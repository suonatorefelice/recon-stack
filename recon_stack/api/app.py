# Costruzione dell'applicazione Flask di recon-api.
#
# Usiamo il modello "application factory" consigliato da Flask: invece di
# creare l'applicazione quando il modulo viene importato, la crea la funzione
# create_app(). Così i test possono costruirne una nuova e pulita per ogni
# prova, e uwsgi (wsgi.py) la crea una volta sola dopo aver letto la
# configurazione.
#
# Per ora l'applicazione ha solo /health. Le risorse /v1/... arrivano con lo
# step 8, l'autenticazione Keystone con lo step 5 (docs/piano.md).
#
# Sviluppo sul Mac, senza DevStack:
#   .venv/bin/flask --app recon_stack.api.app:create_app run --port 5238

import flask


def create_app():
    """Crea e restituisce l'applicazione Flask."""
    app = flask.Flask(__name__)

    @app.get("/health")
    def health():
        # Risponde senza toccare database né OpenStack: dice solo che il
        # processo è acceso e riceve richieste. Lo usano il plugin DevStack e
        # chi amministra il servizio per una verifica rapida con curl.
        # Resterà raggiungibile anche senza token, come gli indirizzi di
        # controllo degli altri componenti OpenStack.
        return flask.jsonify(status="ok")

    return app
