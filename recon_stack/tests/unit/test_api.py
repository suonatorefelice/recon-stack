# Test dell'applicazione web recon-api.
#
# Flask offre un "client di test": simula le richieste HTTP chiamando
# direttamente l'applicazione, senza avviare un server né aprire porte.

from recon_stack.api import app


def make_client():
    return app.create_app().test_client()


def test_health_risponde_ok():
    response = make_client().get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_indirizzo_inesistente_risponde_404():
    response = make_client().get("/non-esiste")
    assert response.status_code == 404
