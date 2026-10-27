# Test della API REST /v1 (api/v1.py) con il client di test di Flask.
#
# Il client di test simula le richieste HTTP chiamando direttamente l'app, senza
# avviare un server. Non c'è Keystone: le intestazioni che normalmente aggiunge
# keystonemiddleware (X-Identity-Status, X-Roles, ...) le mettiamo a mano, come
# farebbe il middleware dopo aver validato un token.

import pytest

from recon_stack import conf
from recon_stack.api import app as app_mod
from recon_stack.db import api as db
from recon_stack.db import migration
from recon_stack.db import models


@pytest.fixture
def client(tmp_path):
    conf.load([])
    conf.CONF.set_override(
        "connection", f"sqlite:///{tmp_path / 'test.sqlite'}", group="database")
    db.reset()
    migration.upgrade()
    yield app_mod.create_app().test_client()
    db.reset()


def _admin(**extra):
    """Intestazioni di un chiamante admin autenticato."""
    h = {
        "X-Identity-Status": "Confirmed",
        "X-User-Id": "user-1",
        "X-User-Name": "admin",
        "X-Project-Id": "progetto-admin",
        "X-Roles": "admin",
    }
    h.update(extra)
    return h


def _member():
    """Intestazioni di un utente autenticato ma senza ruolo admin."""
    return _admin(**{"X-Roles": "member"})


def _seed_scan_done():
    """Crea una scansione completata con host e servizi, e la restituisce."""
    scan = db.create_scan("progetto-1", models.TRIGGER_MANUAL,
                          status=models.SCAN_DONE)
    hosts = db.save_hosts(scan.id, [
        {"ip_address": "10.10.10.5", "network_id": "net-1", "subnet_id": "sub-1",
         "neutron_port_id": "port-1", "server_id": "vm-1", "server_name": "web",
         "classification": models.HOST_KNOWN},
        {"ip_address": "10.10.10.50", "network_id": "net-1", "subnet_id": None,
         "neutron_port_id": None, "server_id": None, "server_name": None,
         "classification": models.HOST_UNKNOWN},
    ])
    web = next(h for h in hosts if h.ip_address == "10.10.10.5")
    db.save_services([
        {"host_id": web.id, "port_number": 22, "protocol": "tcp", "name": "ssh",
         "product": "OpenSSH", "version": "8.9p1", "view": models.VIEW_INTERNAL},
        {"host_id": web.id, "port_number": 80, "protocol": "tcp", "name": "http",
         "product": "nginx", "version": "1.18.0", "view": models.VIEW_INTERNAL},
    ])
    return scan, web


# --- Autenticazione (vale per tutte le rotte /v1) ----------------------------

def test_senza_token_risponde_401(client):
    resp = client.get("/v1/scans")
    assert resp.status_code == 401
    assert "error" in resp.get_json()


def test_utente_non_admin_risponde_403(client):
    resp = client.get("/v1/scans", headers=_member())
    assert resp.status_code == 403


def test_health_resta_pubblico(client):
    # /health non sta sotto /v1: niente token, sempre raggiungibile.
    assert client.get("/health").status_code == 200


# --- Scansioni ---------------------------------------------------------------

def test_elenco_scansioni(client):
    _seed_scan_done()
    resp = client.get("/v1/scans", headers=_admin())
    assert resp.status_code == 200
    scans = resp.get_json()["scans"]
    assert len(scans) == 1
    assert scans[0]["project_id"] == "progetto-1"
    assert scans[0]["status"] == models.SCAN_DONE


def test_diff_scansione(client):
    # Prima scansione: solo la VM web. Seconda: web + un intruso.
    first = db.create_scan("progetto-1", models.TRIGGER_MANUAL,
                           status=models.SCAN_DONE)
    db.save_hosts(first.id, [
        {"ip_address": "10.10.10.5", "network_id": "net-1", "subnet_id": None,
         "neutron_port_id": None, "server_id": None, "server_name": "web",
         "classification": models.HOST_KNOWN}])
    second = db.create_scan("progetto-1", models.TRIGGER_MANUAL,
                            status=models.SCAN_DONE)
    db.save_hosts(second.id, [
        {"ip_address": "10.10.10.5", "network_id": "net-1", "subnet_id": None,
         "neutron_port_id": None, "server_id": None, "server_name": "web",
         "classification": models.HOST_KNOWN},
        {"ip_address": "10.10.10.50", "network_id": "net-1", "subnet_id": None,
         "neutron_port_id": None, "server_id": None, "server_name": None,
         "classification": models.HOST_UNKNOWN}])

    resp = client.get(f"/v1/scans/{second.id}/diff", headers=_admin())
    assert resp.status_code == 200
    diff = resp.get_json()
    assert diff["previous_scan_id"] == first.id
    assert diff["hosts_appeared"] == ["10.10.10.50"]


def test_diff_scansione_inesistente_404(client):
    assert client.get("/v1/scans/x/diff", headers=_admin()).status_code == 404


def test_dettaglio_scansione_e_404(client):
    scan, _ = _seed_scan_done()
    ok = client.get(f"/v1/scans/{scan.id}", headers=_admin())
    assert ok.status_code == 200
    assert ok.get_json()["id"] == scan.id
    assert client.get("/v1/scans/non-esiste", headers=_admin()).status_code == 404


def test_post_scan_admin_accettata_202(client):
    resp = client.post("/v1/scans", headers=_admin(),
                       json={"project_id": "progetto-1"})
    assert resp.status_code == 202
    assert resp.get_json()["status"] == models.SCAN_PENDING
    # Registrata nel log.
    assert len(db.list_scans(project_id="progetto-1")) == 1


def test_post_scan_senza_project_id_400(client):
    resp = client.post("/v1/scans", headers=_admin(), json={})
    assert resp.status_code == 400


def test_post_scan_non_admin_403_ma_registrata(client):
    resp = client.post("/v1/scans", headers=_member(),
                       json={"project_id": "progetto-1"})
    assert resp.status_code == 403
    # Il tentativo rifiutato è comunque nel log (Step 5).
    logged = db.list_scans(project_id="progetto-1")
    assert len(logged) == 1 and logged[0].status == models.SCAN_REJECTED


# --- Host --------------------------------------------------------------------

def test_catalogo_host_ultima_scansione(client):
    _seed_scan_done()
    resp = client.get("/v1/hosts", headers=_admin())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["scan"]["project_id"] == "progetto-1"
    ips = {h["ip_address"] for h in body["hosts"]}
    assert ips == {"10.10.10.5", "10.10.10.50"}


def test_host_filtrati_per_classificazione(client):
    _seed_scan_done()
    resp = client.get("/v1/hosts?classification=unknown", headers=_admin())
    hosts = resp.get_json()["hosts"]
    assert [h["ip_address"] for h in hosts] == ["10.10.10.50"]


def test_dettaglio_host_include_i_servizi(client):
    _, web = _seed_scan_done()
    resp = client.get(f"/v1/hosts/{web.id}", headers=_admin())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["server_name"] == "web"
    names = sorted(s["name"] for s in body["services"])
    assert names == ["http", "ssh"]


def test_host_senza_scansioni_catalogo_vuoto(client):
    # Nessuna scansione DONE: catalogo vuoto, scan a null, non un errore.
    resp = client.get("/v1/hosts", headers=_admin())
    assert resp.status_code == 200
    assert resp.get_json() == {"scan": None, "hosts": []}


# --- Servizi -----------------------------------------------------------------

def test_ricerca_servizi_per_nome(client):
    _seed_scan_done()
    resp = client.get("/v1/services?name=ssh", headers=_admin())
    assert resp.status_code == 200
    services = resp.get_json()["services"]
    assert len(services) == 1
    assert services[0]["name"] == "ssh"
    assert services[0]["product"] == "OpenSSH"


def test_elenco_servizi_del_catalogo(client):
    _seed_scan_done()
    resp = client.get("/v1/services", headers=_admin())
    services = resp.get_json()["services"]
    assert {s["port_number"] for s in services} == {22, 80}
