# Costruzione dell'app Flask di recon-api (application factory: create_app() ne
# crea una nuova, così i test ne hanno una pulita e uwsgi la crea una volta sola
# dopo aver letto la configurazione). Serve /health (pubblico) e la API /v1. I
# gestori di errore traducono eccezioni ed errori HTTP in JSON uniforme
# {"error": "..."}, così un client riceve sempre JSON, mai una pagina HTML.
# install_auth_token avvolge l'app con keystonemiddleware: lo usa solo uwsgi in
# produzione (api/wsgi.py); lo sviluppo locale usa create_app direttamente.
#
# Sviluppo sul Mac:
#   .venv/bin/flask --app recon_stack.api.app:create_app run --port 5238

import flask
from werkzeug import exceptions as http_exc

from recon_stack import conf
from recon_stack.api import context as context_mod
from recon_stack.api import v1


def create_app():
    """Crea e restituisce l'applicazione Flask."""
    app = flask.Flask(__name__)

    @app.get("/health")
    def health():
        # Risponde senza toccare database né OpenStack: dice solo che il processo
        # è acceso. Resta pubblico (senza token), come gli health degli altri
        # componenti OpenStack.
        return flask.jsonify(status="ok")

    app.register_blueprint(v1.bp)
    _register_error_handlers(app)
    return app


def _json_error(code, message):
    """Risposta d'errore uniforme in JSON."""
    return flask.jsonify(error=message), code


def _register_error_handlers(app):
    """Collega le eccezioni del nostro codice al rispettivo codice HTTP."""
    app.register_error_handler(
        context_mod.NotAuthenticated, lambda e: _json_error(401, str(e)))
    app.register_error_handler(
        context_mod.NotAuthorized, lambda e: _json_error(403, str(e)))
    app.register_error_handler(
        v1.RateLimited, lambda e: _json_error(429, str(e)))
    # Errori HTTP standard (400, 404, ...) in JSON invece della pagina di Flask.
    app.register_error_handler(
        http_exc.HTTPException,
        lambda e: _json_error(e.code, e.description))


def install_auth_token(app):
    """Avvolge l'app WSGI con keystonemiddleware (ADR 0002) e la restituisce.

    keystonemiddleware fa validare a Keystone il token X-Auth-Token e aggiunge
    le intestazioni con l'identità (lette in api/context.py). Con
    delay_auth_decision non blocca da solo le richieste senza token: decidiamo
    noi endpoint per endpoint, così /health resta pubblico. L'import è "pigro"
    perché serve solo in produzione (uwsgi), non in sviluppo/test.
    """
    from keystonemiddleware import auth_token

    return auth_token.AuthProtocol(app, {
        "oslo_config_config": conf.CONF,
        "oslo_config_project": "recon-stack",
        "delay_auth_decision": True,
    })
