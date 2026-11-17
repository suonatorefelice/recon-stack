# Test della parte testabile del plugin Horizon (dashboard/api.py).
#
# Il codice dei pannelli Django si verifica su DevStack (dove Horizon gira); qui
# proviamo i pezzi che non dipendono da Horizon: la trasformazione dei dizionari
# in oggetti (wrap) e la sessione che aggiunge il token alle richieste.

import pytest

from recon_stack.dashboard import api


class _Response:
    def __init__(self, status_code=200, payload=None):
        self.raised = False
        self.status_code = status_code
        self._payload = payload or {}
        self.text = ""

    def raise_for_status(self):
        self.raised = True

    def json(self):
        return self._payload


class _Http:
    """Finto `requests.Session`: registra le chiamate e porta un dict headers."""

    def __init__(self):
        self.headers = {}
        self.calls = []
        self.timeouts = []
        self.response = _Response()

    def get(self, url, params=None, timeout=None):
        self.calls.append(("get", url, params))
        self.timeouts.append(timeout)
        return self.response

    def post(self, url, json=None, timeout=None):
        self.calls.append(("post", url, json))
        self.timeouts.append(timeout)
        return self.response


def test_wrap_trasforma_dict_in_oggetto():
    host = api.wrap({"id": "h-1", "ip_address": "10.0.0.5"})
    assert host.id == "h-1"
    assert host.ip_address == "10.0.0.5"


def test_token_session_aggiunge_il_token():
    http = _Http()
    session = api._TokenSession("tok-123", http=http)
    # Il token viene messo nell'header che keystonemiddleware sa leggere.
    assert http.headers["X-Auth-Token"] == "tok-123"

    resp = session.get("http://recon/v1/hosts", params={"name": "ssh"})
    assert http.calls[0] == ("get", "http://recon/v1/hosts", {"name": "ssh"})
    # Non solleva da sola: gli errori li legge ReconClient dallo status.
    assert resp.raised is False


def test_token_session_post_passa_il_corpo_json():
    http = _Http()
    session = api._TokenSession("tok", http=http)
    session.post("http://recon/v1/scans", json={"project_id": "p-1"})
    assert http.calls[0] == ("post", "http://recon/v1/scans", {"project_id": "p-1"})


def test_token_session_imposta_un_timeout_su_ogni_richiesta():
    http = _Http()
    session = api._TokenSession("tok", http=http)
    session.get("http://recon/v1/hosts")
    session.post("http://recon/v1/scans", json={})
    # Senza timeout una recon-api bloccata terrebbe appeso il worker di Horizon.
    assert http.timeouts == [api._HTTP_TIMEOUT, api._HTTP_TIMEOUT]
    assert api._HTTP_TIMEOUT > 0


class _FakeSession:
    """Sessione finta senza catalogo: registra l'URL richiesto."""

    def __init__(self):
        self.urls = []

    def get(self, url, params=None):
        self.urls.append(url)
        return _Response(200, {"scans": [], "findings": [], "hosts": [],
                               "services": []})

    def post(self, url, json=None):
        self.urls.append(url)
        return _Response(200, {})


def test_client_usa_l_endpoint_dato_senza_catalogo():
    # L'endpoint arriva dal chiamante: ReconClient non consulta il catalogo.
    session = _FakeSession()
    client = api.ReconClient(session, "http://recon:5238/")
    client.list_scans()
    client.create_scan("p-1")
    assert session.urls == ["http://recon:5238/v1/scans",
                            "http://recon:5238/v1/scans"]


def test_dashboard_e_client_insieme_mostrano_il_messaggio_della_api():
    # La dashboard usa ReconClient sopra _TokenSession: un errore della API
    # deve arrivare con il suo messaggio, non come errore generico.
    http = _Http()
    http.response = _Response(403, {"error": "ruolo 'admin' richiesto"})
    client = api.ReconClient(api._TokenSession("tok", http=http),
                             endpoint="http://recon:5238")
    with pytest.raises(api.ReconClientError, match="ruolo 'admin' richiesto"):
        client.list_scans()
