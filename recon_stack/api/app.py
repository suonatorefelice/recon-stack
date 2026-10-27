# Costruzione dell'applicazione Flask di recon-api.
#
# Usiamo il modello "application factory" consigliato da Flask: invece di
# creare l'applicazione quando il modulo viene importato, la crea la funzione
# create_app(). Così i test possono costruirne una nuova e pulita per ogni
# prova, e uwsgi (wsgi.py) la crea una volta sola dopo aver letto la
# configurazione.
#
# L'applicazione serve /health (pubblico) e la API REST /v1 (api/v1.py). I
# gestori di errore registrati qui traducono le eccezioni del nostro codice e
# gli errori HTTP in risposte JSON uniformi {"error": "..."}, così un client
# riceve sempre JSON, mai una pagina HTML d'errore.
#
# Sviluppo sul Mac, senza DevStack:
#   .venv/bin/flask --app recon_stack.api.app:create_app run --port 5238

import flask
from werkzeug import exceptions as http_exc

from recon_stack.api import context as context_mod
from recon_stack.api import scans as scans_mod
from recon_stack.api import v1


def create_app():
    """Crea e restituisce l'applicazione Flask."""
    app = flask.Flask(__name__)

    @app.get("/health")
    def health():
        # Risponde senza toccare database né OpenStack: dice solo che il
        # processo è acceso e riceve richieste. Lo usano il plugin DevStack e
        # chi amministra il servizio per una verifica rapida con curl.
        # Resta raggiungibile anche senza token, come gli indirizzi di
        # controllo degli altri componenti OpenStack.
        return flask.jsonify(status="ok")

    app.register_blueprint(v1.bp)
    _register_error_handlers(app)
    return app


def _json_error(code, message):
    """Risposta d'errore uniforme in JSON."""
    return flask.jsonify(error=message), code


def _register_error_handlers(app):
    """Collega le eccezioni del nostro codice al rispettivo codice HTTP.

    Così le rotte possono limitarsi a sollevare l'eccezione giusta (o a
    chiamare funzioni che lo fanno) senza ripetere la gestione della risposta.
    """
    # Autenticazione e autorizzazione (api/context.py).
    app.register_error_handler(
        context_mod.NotAuthenticated, lambda e: _json_error(401, str(e)))
    app.register_error_handler(
        context_mod.NotAuthorized, lambda e: _json_error(403, str(e)))
    # Limite di frequenza delle scansioni (api/scans.py).
    app.register_error_handler(
        scans_mod.RateLimited, lambda e: _json_error(429, str(e)))
    # Errori HTTP standard (400 richiesta malformata, 404 non trovato, ...):
    # li rendiamo in JSON invece della pagina HTML predefinita di Flask.
    app.register_error_handler(
        http_exc.HTTPException,
        lambda e: _json_error(e.code, e.description))
