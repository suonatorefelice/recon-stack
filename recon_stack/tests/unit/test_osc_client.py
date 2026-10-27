# Test del client HTTP dei comandi openstack recon (osc/client.py).
#
# Non serve un vero Keystone né la nostra API in ascolto: passiamo al client una
# "sessione" finta che registra le chiamate e restituisce JSON preparati, come
# farebbe keystoneauth1 dopo aver parlato con l'API.

from recon_stack.osc import client as client_mod


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _Session:
    """Sessione finta: ricorda l'ultima get/post e risponde con payload fissi."""

    def __init__(self, payload=None):
        self.payload = payload or {}
        self.last_get = None
        self.last_post = None

    def get(self, url, params=None):
        self.last_get = (url, params)
        return _Response(self.payload)

    def post(self, url, json=None):
        self.last_post = (url, json)
        return _Response(self.payload)

    def get_endpoint(self, service_type=None, interface=None, region_name=None):
        self.endpoint_query = (service_type, interface, region_name)
        return "http://recon.example:5238/"


def test_list_hosts_costruisce_url_e_filtri():
    session = _Session({"hosts": [{"ip_address": "10.0.0.5"}], "scan": None})
    client = client_mod.ReconClient(session, endpoint="http://recon:5238")
    hosts = client.list_hosts(project_id="p-1", classification="unknown")

    url, params = session.last_get
    assert url == "http://recon:5238/v1/hosts"
    # I parametri non valorizzati (scan_id) non vengono inviati.
    assert params == {"project_id": "p-1", "classification": "unknown"}
    assert hosts == [{"ip_address": "10.0.0.5"}]


def test_list_services_estrae_la_lista():
    session = _Session({"services": [{"name": "ssh"}], "scan": None})
    client = client_mod.ReconClient(session, endpoint="http://recon:5238")
    assert client.list_services(name="ssh") == [{"name": "ssh"}]
    assert session.last_get[1] == {"name": "ssh"}


def test_get_scan_exposure_estrae_le_segnalazioni():
    session = _Session({"findings": [{"type": "overexposed"}], "scan": None})
    client = client_mod.ReconClient(session, endpoint="http://recon:5238")
    findings = client.get_scan_exposure("s-1", severity="high")

    url, params = session.last_get
    assert url == "http://recon:5238/v1/scans/s-1/exposure"
    assert params == {"severity": "high"}
    assert findings == [{"type": "overexposed"}]


def test_create_scan_fa_una_post_con_project_id():
    session = _Session({"id": "scan-1", "status": "PENDING"})
    client = client_mod.ReconClient(session, endpoint="http://recon:5238")
    scan = client.create_scan("progetto-1")

    url, body = session.last_post
    assert url == "http://recon:5238/v1/scans"
    assert body == {"project_id": "progetto-1"}
    assert scan["status"] == "PENDING"


def test_endpoint_preso_dal_catalogo_se_non_dato():
    session = _Session({"scans": []})
    client = client_mod.ReconClient(session, interface="internal")
    client.list_scans()
    # Ha chiesto l'endpoint al catalogo col nostro service type e l'interfaccia.
    assert session.endpoint_query == ("recon", "internal", None)
    # E l'ha usato togliendo la barra finale.
    assert session.last_get[0] == "http://recon.example:5238/v1/scans"
