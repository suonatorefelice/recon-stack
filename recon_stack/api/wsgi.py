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

conf.load()
application = app.create_app()
