# Test dell'aggancio di keystonemiddleware (api/middleware.py).
#
# Non abbiamo un Keystone a cui parlare: ma possiamo verificare il
# comportamento che ci serve senza token, cioè che /health resti pubblico.
# In modalità delay_auth_decision il middleware, se non c'è un token, non
# contatta Keystone e lascia passare la richiesta: /health risponde lo stesso.

from werkzeug.test import Client

from recon_stack import conf
from recon_stack.api import app
from recon_stack.api import middleware


def test_health_resta_pubblico_attraverso_il_middleware():
    conf.load([])
    wrapped = middleware.install_auth_token(app.create_app())
    response = Client(wrapped).get("/health")
    assert response.status_code == 200
