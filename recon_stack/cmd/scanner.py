# Il processo recon-scanner (ADR 0004).
#
# È un programma che resta acceso e, grazie ad APScheduler, esegue dei
# compiti a intervalli regolari. È separato da recon-api perché le scansioni
# durano a lungo: dentro il server web bloccherebbero le richieste, e con più
# processi web partirebbero più volte.
#
# I compiti periodici del processo (docs/piano.md):
#   - heartbeat: una riga nel log a ogni intervallo, per vedere che è vivo;
#   - run_pending_scans (Step 10): esegue le scansioni in attesa (PENDING)
#     create da POST /v1/scans — è il ponte fra la API e l'esecuzione (ADR 0004);
#   - enqueue_periodic_scans (Step 10): a intervalli regolari accoda una
#     scansione periodica per i progetti configurati.
#
# Avvio:
#   recon-stack-scanner                          (cerca da solo recon-stack.conf)
#   recon-stack-scanner --config-file file.conf  (file indicato a mano)
# In DevStack lo avvia il plugin come servizio devstack@recon-scanner.

import logging
import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler

from recon_stack import conf
from recon_stack.db import api as db
from recon_stack.db import models
from recon_stack.scanner import cloud
from recon_stack.scanner import scan as scan_mod

LOG = logging.getLogger(__name__)


def heartbeat():
    """Compito periodico di prova: dice nel log che il processo è attivo."""
    LOG.info("recon-scanner attivo")


def run_pending_scans(connect=None):
    """Esegue le scansioni in attesa (PENDING), dalla più vecchia alla più nuova.

    connect è la funzione che apre la connessione a OpenStack: iniettabile nei
    test. Se non ci sono scansioni in attesa non apre nemmeno la connessione.
    Un errore su una scansione non ferma le altre né il processo.
    """
    pending = db.list_scans(status=models.SCAN_PENDING)
    if not pending:
        return
    connect = connect or cloud.connect
    try:
        conn = connect()
    except Exception:
        LOG.exception("connessione a OpenStack fallita: riprovo al prossimo giro")
        return
    # list_scans torna dalla più recente: le eseguiamo dalla più vecchia.
    for scan in reversed(pending):
        try:
            scan_mod.run_scan(conn, scan.id)
        except Exception:
            LOG.exception("esecuzione della scansione %s fallita", scan.id)


def enqueue_periodic_scans(connect=None):
    """Accoda una scansione periodica (PENDING) per ogni progetto configurato.

    Le scansioni accodate le esegue run_pending_scans al giro successivo, come
    quelle chieste dalla API. I progetti sono in [scanner] periodic_projects
    (nomi o id); li risolviamo in id tramite la connessione.
    """
    projects = conf.CONF.scanner.periodic_projects
    if not projects:
        return
    connect = connect or cloud.connect
    try:
        conn = connect()
    except Exception:
        LOG.exception("connessione a OpenStack fallita: salto le scansioni periodiche")
        return
    for name_or_id in projects:
        project = conn.identity.find_project(name_or_id, ignore_missing=True)
        if project is None:
            LOG.warning("progetto periodico '%s' non trovato: salto", name_or_id)
            continue
        db.create_scan(project.id, models.TRIGGER_PERIODIC,
                       status=models.SCAN_PENDING)
        LOG.info("scansione periodica accodata per il progetto %s", project.id)


def build_scheduler():
    """Crea lo scheduler con i compiti periodici del processo.

    BlockingScheduler, quando viene avviato, occupa il programma e non
    restituisce il controllo finché non viene fermato: è il tipo giusto per un
    processo che esiste solo per eseguire compiti pianificati.

    Gli intervalli a 0 disattivano il compito corrispondente (vedi conf.py):
    l'esecutore delle PENDING e le scansioni periodiche si aggiungono solo se
    configurati.
    """
    scheduler = BlockingScheduler()
    scheduler.add_job(
        heartbeat,
        "interval",
        seconds=conf.CONF.scanner.heartbeat_interval,
        id="heartbeat",
        # Se un'esecuzione è ancora in corso quando arriva la successiva, la
        # successiva salta invece di sovrapporsi. Per le scansioni questo
        # impedisce due esecuzioni insieme.
        max_instances=1,
        coalesce=True,
    )

    poll = conf.CONF.scanner.scan_poll_interval
    if poll > 0:
        scheduler.add_job(
            run_pending_scans, "interval", seconds=poll,
            id="run_pending_scans", max_instances=1, coalesce=True)

    periodic = conf.CONF.scanner.periodic_scan_interval
    if periodic > 0 and conf.CONF.scanner.periodic_projects:
        scheduler.add_job(
            enqueue_periodic_scans, "interval", seconds=periodic,
            id="enqueue_periodic_scans", max_instances=1, coalesce=True)

    return scheduler


def main(argv=None):
    """Punto d'ingresso del comando recon-stack-scanner (vedi setup.cfg)."""
    conf.load(sys.argv[1:] if argv is None else argv)
    scheduler = build_scheduler()

    # Quando DevStack ferma il servizio (unstack.sh), systemd manda al
    # processo il segnale SIGTERM. Lo intercettiamo per fermare lo scheduler
    # in modo ordinato, invece di interrompere a metà un compito in corso.
    def stop(signum, frame):
        LOG.info("segnale %s ricevuto, arresto di recon-scanner", signum)
        scheduler.shutdown(wait=False)

    signal.signal(signal.SIGTERM, stop)

    LOG.info("recon-scanner avviato, battito ogni %s secondi",
             conf.CONF.scanner.heartbeat_interval)
    heartbeat()  # un primo battito subito, senza aspettare l'intervallo
    try:
        scheduler.start()
    except KeyboardInterrupt:
        # Ctrl+C quando lo si lancia a mano durante lo sviluppo.
        LOG.info("interrotto da tastiera")
    LOG.info("recon-scanner fermato")


if __name__ == "__main__":
    main()
