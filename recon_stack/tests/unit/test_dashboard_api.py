# Test della parte testabile del plugin Horizon (dashboard/api.py).
#
# Il codice dei pannelli Django si verifica su DevStack (dove Horizon gira); qui
# proviamo i pezzi che non dipendono da Horizon: la trasformazione dei dizionari
# in oggetti (wrap) e la sessione che aggiunge il token alle richieste.

from recon_stack.dashboard import api


class _Response:
    def __init__(self):
        self.raised = False

    def raise_for_status(self):
        self.raised = True


class _Http:
    """Finto `requests.Session`: registra le chiamate e porta un dict headers."""

    def __init__(self):
        self.headers = {}
        self.calls = []
        self.response = _Response()

    def get(self, url, params=None):
        self.calls.append(("get", url, params))
        return self.response

    def post(self, url, json=None):
        self.calls.append(("post", url, json))
        return self.response


def test_wrap_trasforma_dict_in_oggetto():
    host = api.wrap({"id": "h-1", "ip_address": "10.0.0.5"})
    assert host.id == "h-1"
    assert host.ip_address == "10.0.0.5"


def test_token_session_aggiunge_il_token_e_solleva_sugli_errori():
    http = _Http()
    session = api._TokenSession("tok-123", http=http)
    # Il token viene messo nell'header che keystonemiddleware sa leggere.
    assert http.headers["X-Auth-Token"] == "tok-123"

    resp = session.get("http://recon/v1/hosts", params={"name": "ssh"})
    assert http.calls[0] == ("get", "http://recon/v1/hosts", {"name": "ssh"})
    # raise_for_status è stato invocato: un 4xx/5xx diventerebbe un'eccezione.
    assert resp.raised is True


def test_token_session_post_passa_il_corpo_json():
    http = _Http()
    session = api._TokenSession("tok", http=http)
    session.post("http://recon/v1/scans", json={"project_id": "p-1"})
    assert http.calls[0] == ("post", "http://recon/v1/scans", {"project_id": "p-1"})
