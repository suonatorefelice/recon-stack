# La API REST versione 1: /v1/scans, /v1/hosts, /v1/services (Step 8).
#
# Espone via HTTP ciò che gli step precedenti hanno salvato nel database. È un
# "blueprint" di Flask: un gruppo di rotte con prefisso comune (/v1) che l'app
# principale (api/app.py) aggancia. Le rotte fanno poco: leggono i parametri,
# chiamano il livello dati (db/api.py) e trasformano gli oggetti in JSON con i
# serializzatori qui sotto.
#
# Autenticazione (ADR 0002, Step 8): tutte le rotte /v1 richiedono il ruolo
# admin. Chi siamo lo dice Keystone tramite le intestazioni aggiunte dal
# middleware (api/context.py); qui le leggiamo e pretendiamo l'admin. Gli errori
# di autenticazione/autorizzazione diventano 401/403 grazie ai gestori
# registrati in api/app.py, che traducono le eccezioni in risposte JSON.
#
# Il "catalogo" (GET /v1/hosts e /v1/services) sono i risultati di UNA
# scansione, scelta così (vedi _resolve_scan):
#   - ?scan_id=<id>    una scansione precisa;
#   - ?project_id=<id> l'ultima scansione completata (DONE) di quel progetto;
#   - niente           l'ultima scansione completata in assoluto.

import json

import flask

from recon_stack.api import context as context_mod
from recon_stack.api import scans as scans_mod
from recon_stack.db import api as db
from recon_stack.db import models

bp = flask.Blueprint("v1", __name__, url_prefix="/v1")


# --- Serializzatori: da oggetti del database a dizionari JSON -----------------

def _iso(dt):
    """Data/ora in formato ISO 8601, oppure None. Le salviamo in UTC (models)."""
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


def _service_dict(service):
    """Rappresentazione di un servizio in ascolto su un host."""
    return {
        "id": service.id,
        "host_id": service.host_id,
        "port_number": service.port_number,
        "protocol": service.protocol,
        "name": service.name,
        "product": service.product,
        "version": service.version,
        "view": service.view,
    }


# --- Autenticazione e scelta della scansione ---------------------------------

def _require_admin():
    """Costruisce il contesto dalle intestazioni e pretende il ruolo admin.

    Solleva NotAuthenticated/NotAuthorized, tradotte in 401/403 dai gestori di
    errore registrati in api/app.py.
    """
    ctx = context_mod.RequestContext.from_headers(flask.request.headers)
    ctx.require_admin()
    return ctx


def _resolve_scan():
    """Decide su quale scansione lavorano /v1/hosts e /v1/services.

    Restituisce la scansione scelta (vedi il commento in testa al file) o None
    se non ce n'è una adatta (nessuna scansione completata).
    """
    scan_id = flask.request.args.get("scan_id")
    if scan_id:
        scan = db.get_scan(scan_id)
        if scan is None:
            flask.abort(404, f"scansione '{scan_id}' non trovata")
        return scan
    project_id = flask.request.args.get("project_id")
    return db.get_latest_scan(project_id=project_id, status=models.SCAN_DONE)


# --- Scansioni ---------------------------------------------------------------

@bp.get("/scans")
def list_scans():
    """Elenco delle scansioni, filtrabile per ?project_id= e ?status=."""
    _require_admin()
    scans = db.list_scans(
        project_id=flask.request.args.get("project_id"),
        status=flask.request.args.get("status"))
    return flask.jsonify(scans=[_scan_dict(s) for s in scans])


@bp.get("/scans/<scan_id>")
def get_scan(scan_id):
    """Dettaglio di una scansione: stato, perimetro, chi l'ha chiesta."""
    _require_admin()
    scan = db.get_scan(scan_id)
    if scan is None:
        flask.abort(404, f"scansione '{scan_id}' non trovata")
    return flask.jsonify(_scan_dict(scan))


@bp.post("/scans")
def create_scan():
    """Richiede una nuova scansione manuale di un progetto.

    Il corpo JSON deve avere project_id. Le regole d'avvio (ruolo admin, limite
    di frequenza) e la registrazione nel log sono in api/scans.request_scan
    (Step 5): qui ci limitiamo a passargli il contesto. In caso di accettazione
    risponde 202 con la scansione creata (stato PENDING); la eseguirà lo scanner.
    """
    ctx = context_mod.RequestContext.from_headers(flask.request.headers)
    data = flask.request.get_json(silent=True) or {}
    project_id = data.get("project_id")
    if not project_id:
        flask.abort(400, "il corpo JSON deve contenere project_id")
    # request_scan controlla il ruolo e la frequenza, registra il tentativo e,
    # se rifiuta, solleva l'eccezione che i gestori traducono in 401/403/429.
    scan = scans_mod.request_scan(ctx, project_id)
    response = flask.jsonify(_scan_dict(scan))
    response.status_code = 202
    return response


# --- Host --------------------------------------------------------------------

@bp.get("/hosts")
def list_hosts():
    """Host del catalogo, filtrabili per ?classification= (known/unknown/absent)."""
    _require_admin()
    scan = _resolve_scan()
    if scan is None:
        return flask.jsonify(scan=None, hosts=[])
    hosts = db.get_hosts(
        scan.id, classification=flask.request.args.get("classification"))
    return flask.jsonify(scan=_scan_ref(scan),
                         hosts=[_host_dict(h) for h in hosts])


@bp.get("/hosts/<host_id>")
def get_host(host_id):
    """Dettaglio di un host, con l'elenco dei servizi trovati su di esso."""
    _require_admin()
    host = db.get_host(host_id)
    if host is None:
        flask.abort(404, f"host '{host_id}' non trovato")
    result = _host_dict(host)
    result["services"] = [_service_dict(s)
                          for s in db.get_services(host_id=host.id)]
    return flask.jsonify(result)


# --- Servizi -----------------------------------------------------------------

@bp.get("/services")
def list_services():
    """Servizi del catalogo, cercabili per ?name= (es. ?name=ssh)."""
    _require_admin()
    scan = _resolve_scan()
    if scan is None:
        return flask.jsonify(scan=None, services=[])
    services = db.get_services(
        scan_id=scan.id, name=flask.request.args.get("name"))
    return flask.jsonify(scan=_scan_ref(scan),
                         services=[_service_dict(s) for s in services])
