# API REST v1: /v1/scans, /v1/hosts, /v1/services. Espone via HTTP
# quanto salvato nel database. È un blueprint Flask agganciato da api/app.py;
# le rotte leggono i parametri, chiamano db/api.py e serializzano in JSON.
# Tutte le rotte /v1 richiedono il ruolo admin (ADR 0002): chi siamo lo dicono
# le intestazioni di Keystone lette da api/context.py; gli errori diventano
# 401/403 grazie ai gestori in api/app.py.
#
# Il "catalogo" (/v1/hosts, /v1/services) è una scansione sola, scelta così
# (_resolve_scan): ?scan_id=<id> una precisa; ?project_id=<id> l'ultima DONE di
# quel progetto; niente, l'ultima DONE in assoluto.

import json
import logging
import threading

import flask

from recon_stack import conf
from recon_stack.api import context as context_mod
from recon_stack.db import api as db
from recon_stack.db import models
from recon_stack.scanner import cloud
from recon_stack.scanner import diff as diff_mod
from recon_stack.scanner import runner

bp = flask.Blueprint("v1", __name__, url_prefix="/v1")
LOG = logging.getLogger(__name__)


# Serializzatori: da oggetti del database a dizionari JSON

def _iso(dt):
    """Data/ora in ISO 8601 (o None). Salvate in UTC (models)."""
    return dt.isoformat() if dt is not None else None


def _scan_dict(scan):
    """Rappresentazione completa di una scansione."""
    return {
        "id": scan.id,
        "project_id": scan.project_id,
        "trigger": scan.trigger,
        "status": scan.status,
        "requested_by_user": scan.requested_by_user,
        "requested_by_project": scan.requested_by_project,
        "created_at": _iso(scan.created_at),
        "started_at": _iso(scan.started_at),
        "finished_at": _iso(scan.finished_at),
        # perimeter è salvato come testo JSON: lo riconvertiamo in oggetto.
        "perimeter": json.loads(scan.perimeter) if scan.perimeter else None,
        "fault": scan.fault,
        "phase": scan.phase,  # fase corrente se in corso, per l'avanzamento
    }


def _scan_ref(scan):
    """Riferimento sintetico alla scansione da cui viene un catalogo."""
    return {
        "id": scan.id,
        "project_id": scan.project_id,
        "finished_at": _iso(scan.finished_at),
    }


def _host_dict(host):
    """Rappresentazione di un host (senza i servizi: li aggiunge il dettaglio)."""
    return {
        "id": host.id,
        "scan_id": host.scan_id,
        "ip_address": host.ip_address,
        "network_id": host.network_id,
        "subnet_id": host.subnet_id,
        "neutron_port_id": host.neutron_port_id,
        "server_id": host.server_id,
        "server_name": host.server_name,
        "classification": host.classification,
    }


def _finding_dict(finding):
    """Rappresentazione di una segnalazione di esposizione."""
    return {
        "id": finding.id,
        "scan_id": finding.scan_id,
        "type": finding.finding_type,
        "severity": finding.severity,
        "ip_address": finding.ip_address,
        "port_number": finding.port_number,
        "protocol": finding.protocol,
        "message": finding.message,
    }


def _service_dict(service):
    """Rappresentazione di un servizio in ascolto su un host."""
    return {
        "id": service.id,
        "host_id": service.host_id,
        # L'IP dell'host, così chi cerca un servizio vede subito dove sta.
        "ip_address": service.host.ip_address,
        "port_number": service.port_number,
        "protocol": service.protocol,
        "name": service.name,
        "product": service.product,
        "version": service.version,
        "view": service.view,
    }


# Autenticazione e scelta della scansione

@bp.before_request
def _authorize():
    """Un solo controllo per tutto /v1: serve un chiamante admin autenticato.

    Gira prima di ogni rotta, quindi un rifiuto (401/403) non scrive nulla nel
    database. Il contesto resta in flask.g.context per le rotte che lo usano.
    """
    ctx = context_mod.RequestContext.from_headers(flask.request.headers)
    ctx.require_admin()
    flask.g.context = ctx


def _resolve_scan():
    """La scansione su cui lavorano /v1/hosts e /v1/services (vedi testa file)."""
    scan_id = flask.request.args.get("scan_id")
    if scan_id:
        scan = db.get_scan(scan_id)
        if scan is None:
            flask.abort(404, f"scansione '{scan_id}' non trovata")
        return scan
    project_id = flask.request.args.get("project_id")
    return db.get_latest_scan(project_id=project_id, status=models.SCAN_DONE)


# Scansioni

@bp.get("/scans")
def list_scans():
    """Elenco delle scansioni, filtrabile per ?status=."""
    scans = db.list_scans(status=flask.request.args.get("status"))
    return flask.jsonify(scans=[_scan_dict(s) for s in scans])


@bp.get("/scans/<scan_id>")
def get_scan(scan_id):
    """Dettaglio di una scansione: stato, perimetro, chi l'ha chiesta."""
    scan = db.get_scan(scan_id)
    if scan is None:
        flask.abort(404, f"scansione '{scan_id}' non trovata")
    return flask.jsonify(_scan_dict(scan))


@bp.get("/scans/<scan_id>/diff")
def get_scan_diff(scan_id):
    """Confronto con la scansione precedente completata dello stesso progetto."""
    diff = diff_mod.diff_for_scan(scan_id)
    if diff is None:
        flask.abort(404, f"scansione '{scan_id}' non trovata")
    return flask.jsonify(diff)


@bp.get("/scans/<scan_id>/exposure")
def get_scan_exposure(scan_id):
    """Segnalazioni di esposizione di una scansione (ordinate dalla più grave)."""
    scan = db.get_scan(scan_id)
    if scan is None:
        flask.abort(404, f"scansione '{scan_id}' non trovata")
    findings = db.get_findings(scan_id)
    return flask.jsonify(scan=_scan_ref(scan),
                         findings=[_finding_dict(f) for f in findings])


@bp.post("/scans")
def create_scan():
    """Richiede una nuova scansione manuale (corpo JSON con project_id).

    Le regole d'avvio (admin, frequenza) e il log sono in request_scan (in fondo
    a questo file); in caso di accettazione avvia la scansione in un thread
    (scanner/runner.py) e risponde 202 con la scansione PENDING.
    """
    ctx = flask.g.context
    data = flask.request.get_json(silent=True) or {}
    project_id = data.get("project_id")
    if not project_id:
        flask.abort(400, "il corpo JSON deve contenere project_id")
    scan = request_scan(ctx, project_id)
    # Esecuzione in-process: il thread parte ora, noi rispondiamo subito 202 e
    # il client segue lo stato con GET /v1/scans/<id>.
    runner.start_scan(scan.id)
    response = flask.jsonify(_scan_dict(scan))
    response.status_code = 202
    return response


# Host

@bp.get("/hosts")
def list_hosts():
    """Host del catalogo di una scansione (vedi _resolve_scan)."""
    scan = _resolve_scan()
    if scan is None:
        return flask.jsonify(scan=None, hosts=[])
    hosts = db.get_hosts(scan.id)
    return flask.jsonify(scan=_scan_ref(scan),
                         hosts=[_host_dict(h) for h in hosts])


@bp.get("/hosts/<host_id>")
def get_host(host_id):
    """Dettaglio di un host, con i servizi trovati su di esso."""
    host = db.get_host(host_id)
    if host is None:
        flask.abort(404, f"host '{host_id}' non trovato")
    result = _host_dict(host)
    result["services"] = [_service_dict(s)
                          for s in db.get_services(host_id=host.id)]
    return flask.jsonify(result)


# Servizi

@bp.get("/services")
def list_services():
    """Servizi del catalogo, cercabili per ?name= (es. ?name=ssh)."""
    scan = _resolve_scan()
    if scan is None:
        return flask.jsonify(scan=None, services=[])
    services = db.get_services(
        scan_id=scan.id, name=flask.request.args.get("name"))
    return flask.jsonify(scan=_scan_ref(scan),
                         services=[_service_dict(s) for s in services])


# Regole d'avvio di una scansione, usate dalla rotta POST /scans qui
# sopra. Il ruolo admin è già stato controllato dall'hook _authorize, quindi
# qui resta solo la frequenza (una ogni [scanner] min_scan_interval secondi per
# progetto). Una richiesta accettata nasce PENDING (lo esegue il thread di
# scanner/runner.py); una troppo frequente solleva RateLimited (429) e non
# scrive nulla nel database. Il perimetro si controlla all'esecuzione, non qui
# (scanner/perimeter.py, ADR 0005).

class RateLimited(Exception):
    """Richiesta rifiutata perché arrivata troppo presto dopo la precedente."""


# Rende atomico "leggi l'ultima scansione del progetto + crea la nuova", così
# due richieste simultanee non passano entrambe il limite. Basta un lock in
# memoria perché il servizio gira in un solo processo (uwsgi processes=1).
_scan_lock = threading.Lock()


def _seconds_since_last_scan(project_id):
    """Secondi dall'ultima scansione del progetto (None se nessuna)."""
    last = db.get_latest_scan(project_id=project_id, status=None)
    if last is None:
        return None
    return (models.utcnow() - last.created_at).total_seconds()


def request_scan(context, project_id, connect=None):
    """Valuta la frequenza e crea una scansione manuale PENDING.

    `project_id` può essere il nome o l'id del progetto: viene risolto a id
    canonico con Keystone (`connect` permette di iniettare la connessione; di
    default cloud.connect). Se il progetto non esiste risponde 404. L'id
    canonico vale sia per il limite di frequenza sia per la scansione, così il
    limite non si aggira alternando nome e id.

    Se la richiesta è troppo ravvicinata alla precedente solleva RateLimited
    (tradotta in 429) senza scrivere nulla.
    """
    conn = (connect or cloud.connect)()
    project = conn.identity.find_project(project_id, ignore_missing=True)
    if project is None:
        flask.abort(404, f"progetto '{project_id}' non trovato")
    # Da qui in poi solo l'id canonico: il limite di frequenza conta per id,
    # quindi chiedere "recon-demo" e poi il suo id non lo aggira.
    project_id = project.id

    min_interval = conf.CONF.scanner.min_scan_interval
    with _scan_lock:
        if min_interval > 0:
            elapsed = _seconds_since_last_scan(project_id)
            if elapsed is not None and elapsed < min_interval:
                wait = int(min_interval - elapsed)
                LOG.warning("scansione rifiutata (progetto %s, utente %s): "
                            "troppo frequente, attendere ancora %s s",
                            project_id, context.user_id, wait)
                raise RateLimited(f"riprovare fra {wait} s")

        scan = db.create_scan(
            project_id, models.TRIGGER_MANUAL,
            requested_by_user=context.user_id,
            requested_by_project=context.project_id,
            status=models.SCAN_PENDING)
    LOG.info("scansione accettata (progetto %s, utente %s): %s",
             project_id, context.user_id, scan.id)
    return scan
