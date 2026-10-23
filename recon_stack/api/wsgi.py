# Punto d'ingresso per uwsgi (ADR 0008).
#
# WSGI è lo standard con cui un server web Python (qui uwsgi) passa le
# richieste HTTP a un'applicazione. uwsgi importa questo modulo e usa la
# variabile "application": il plugin DevStack glielo dice con
# recon_stack.api.wsgi:application (devstack/plugin.sh).
#
# Prima di creare l'applicazione si legge la configurazione: uwsgi non passa
# argomenti, quindi oslo.config cerca da solo /etc/recon-stack/recon-stack.conf
# (vedi recon_stack/conf.py).

from recon_stack import conf
from recon_stack.api import app
from recon_stack.api import middleware

conf.load()
# keystonemiddleware valida il token e aggiunge le intestazioni con l'identità
# (ADR 0002). Lo mettiamo solo qui, nel percorso di produzione (uwsgi): lo
# sviluppo locale usa direttamente create_app, senza Keystone.
application = middleware.install_auth_token(app.create_app())
