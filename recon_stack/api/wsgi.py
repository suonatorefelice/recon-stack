# Punto d'ingresso per uwsgi (ADR 0008): uwsgi importa questo modulo e serve la
# variabile "application". Prima leggiamo la configurazione (uwsgi non passa
# argomenti, oslo.config cerca /etc/recon-stack/recon-stack.conf da solo).

from recon_stack import conf
from recon_stack.api import app
from recon_stack.scanner import runner

conf.load()
# Le scansioni rimaste PENDING o RUNNING da un riavvio non le esegue più
# nessuno: le chiudiamo come FAILED, così chi fa polling vede una fine.
runner.fail_orphan_scans()
# Scansioni periodiche: lo scheduler parte qui, una volta, nel processo uwsgi.
# create_app (test, flask run) non lo avvia.
runner.start_scheduler()
# keystonemiddleware solo qui, nel percorso di produzione (uwsgi); lo sviluppo
# locale usa create_app direttamente, senza Keystone.
application = app.install_auth_token(app.create_app())
