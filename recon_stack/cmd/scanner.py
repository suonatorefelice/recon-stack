# Il processo recon-scanner (ADR 0004).
#
# È un programma che resta acceso e, grazie ad APScheduler, esegue dei
# compiti a intervalli regolari. È separato da recon-api perché le scansioni
# durano a lungo: dentro il server web bloccherebbero le richieste, e con più
# processi web partirebbero più volte.
#
# Per ora l'unico compito è il "battito" (heartbeat): una riga nel log a ogni
# intervallo, per verificare che il processo sia vivo. I compiti veri, cioè
# eseguire le scansioni richieste e quelle periodiche, arrivano con gli step
# 6 e 10 (docs/piano.md).
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

LOG = logging.getLogger(__name__)


def heartbeat():
    """Compito periodico di prova: dice nel log che il processo è attivo."""
    LOG.info("recon-scanner attivo")


def build_scheduler():
    """Crea lo scheduler con i compiti periodici del processo.

    BlockingScheduler, quando viene avviato, occupa il programma e non
    restituisce il controllo finché non viene fermato: è il tipo giusto per un
    processo che esiste solo per eseguire compiti pianificati.
    """
    scheduler = BlockingScheduler()
    scheduler.add_job(
        heartbeat,
        "interval",
        seconds=conf.CONF.scanner.heartbeat_interval,
        id="heartbeat",
        # Se un'esecuzione è ancora in corso quando arriva la successiva, la
        # successiva salta invece di sovrapporsi. Per il battito non cambia
        # niente; per le scansioni, che useranno la stessa impostazione,
        # impedisce due scansioni dello stesso progetto insieme.
        max_instances=1,
        coalesce=True,
    )
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
