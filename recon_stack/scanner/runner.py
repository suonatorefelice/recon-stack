# Esecuzione delle scansioni dentro il server API, senza un processo separato.
# POST /v1/scans avvia un thread di sfondo (start_scan) e risponde subito 202;
# il client segue l'avanzamento facendo polling su GET /v1/scans/<id> (stato
# PENDING -> RUNNING -> DONE/FAILED). Le scansioni periodiche le avvia un
# BackgroundScheduler (APScheduler) nello stesso processo uwsgi.

import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler

from recon_stack import conf
from recon_stack.db import api as db
from recon_stack.db import models
from recon_stack.scanner import cloud
from recon_stack.scanner import scan as scan_mod

LOG = logging.getLogger(__name__)

# Riferimento allo scheduler già avviato: serve a non avviarne due se
# start_scheduler viene chiamata più volte.
_scheduler = None


def _esegui(scan_id, connect):
    """Corpo del thread: connessione a OpenStack e scansione.

    Lo stato FAILED viene scritto in un solo punto per ogni caso. Se la
    connessione fallisce run_scan non parte, quindi lo scriviamo qui; se invece
    parte, è run_scan a segnare FAILED e a rilanciare l'errore, e qui ci
    limitiamo a registrarlo nel log.
    """
    try:
        conn = (connect or cloud.connect)()
    except Exception as exc:
        LOG.exception("scansione %s: connessione a OpenStack fallita", scan_id)
        db.update_scan(scan_id, status=models.SCAN_FAILED,
                       finished_at=models.utcnow(), fault=str(exc))
        return
    try:
        scan_mod.run_scan(conn, scan_id)
    except Exception:
        # run_scan ha già segnato FAILED con il motivo.
        LOG.exception("scansione %s fallita", scan_id)


def start_scan(scan_id, connect=None):
    """Avvia la scansione in un thread daemon e restituisce il Thread già
    partito (i test lo attendono con join()). `connect` permette di iniettare
    la connessione; di default si usa cloud.connect."""
    thread = threading.Thread(target=_esegui, args=(scan_id, connect),
                              name=f"scan-{scan_id}", daemon=True)
    thread.start()
    return thread


def run_periodic_scans(connect=None):
    """Scansione periodica: per ogni progetto configurato crea una scansione
    e la esegue subito, in linea (siamo già nel thread dello scheduler).

    I progetti sono in [scanner] periodic_projects (nomi o id). Un errore su un
    progetto non ferma gli altri. Senza progetti non apre nemmeno la connessione.
    """
    projects = conf.CONF.scanner.periodic_projects
    if not projects:
        return
    try:
        conn = (connect or cloud.connect)()
    except Exception:
        LOG.exception("connessione a OpenStack fallita: salto le scansioni periodiche")
        return
    for name_or_id in projects:
        try:
            project = conn.identity.find_project(name_or_id, ignore_missing=True)
            if project is None:
                LOG.warning("progetto periodico '%s' non trovato: salto", name_or_id)
                continue
            scan = db.create_scan(project.id, models.TRIGGER_PERIODIC,
                                  status=models.SCAN_PENDING)
            scan_mod.run_scan(conn, scan.id)
        except Exception:
            LOG.exception("scansione periodica del progetto '%s' fallita", name_or_id)


def build_scheduler():
    """Crea lo scheduler (senza avviarlo). Il job periodico c'è solo se
    l'intervallo è > 0 e ci sono progetti: altrimenti lo scheduler è vuoto."""
    scheduler = BackgroundScheduler()
    interval = conf.CONF.scanner.periodic_scan_interval
    if interval > 0 and conf.CONF.scanner.periodic_projects:
        scheduler.add_job(
            run_periodic_scans, trigger="interval", seconds=interval,
            id="periodic_scans",
            # Un solo giro alla volta (max_instances=1): se uno dura più
            # dell'intervallo, quello successivo salta. coalesce=True evita che
            # i giri mancati si accumulino e partano tutti insieme.
            max_instances=1, coalesce=True)
    return scheduler


def start_scheduler():
    """Costruisce e avvia lo scheduler una sola volta per processo."""
    global _scheduler
    if _scheduler is None:
        _scheduler = build_scheduler()
        _scheduler.start()
    return _scheduler


def fail_orphan_scans():
    """Chiude come FAILED le scansioni rimaste RUNNING/PENDING da un avvio
    precedente. Il thread di scansione muore insieme al processo: se il server
    si riavvia a metà, la riga resta orfana e chi fa polling su
    GET /v1/scans/<id> non vedrebbe mai la fine. Ritorna quante ne ha chiuse."""
    chiuse = 0
    for status in (models.SCAN_RUNNING, models.SCAN_PENDING):
        for scan in db.list_scans(status=status):
            db.update_scan(scan.id, status=models.SCAN_FAILED,
                           fault="interrotta da un riavvio del server",
                           finished_at=models.utcnow())
            chiuse += 1
    return chiuse
