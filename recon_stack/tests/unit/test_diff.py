# Test del confronto fra scansioni (scanner/diff.py).
#
# diff_snapshots e snapshot non toccano il database: li proviamo con oggetti
# finti. diff_for_scan legge dal database: lo proviamo seminando due scansioni.

import types

import pytest

from recon_stack import conf
from recon_stack.db import api as db
from recon_stack.db import migration
from recon_stack.db import models
from recon_stack.scanner import diff as diff_mod


def _host(id, ip, classification=models.HOST_KNOWN):
    return types.SimpleNamespace(id=id, ip_address=ip, classification=classification)


def _service(host_id, port, name="ssh", protocol="tcp"):
    return types.SimpleNamespace(host_id=host_id, port_number=port,
                                 protocol=protocol, name=name)


# --- snapshot + diff_snapshots (puri) ----------------------------------------

def test_snapshot_lega_i_servizi_all_ip_dell_host():
    hosts = [_host("h-1", "10.0.0.5")]
    services = [_service("h-1", 22), _service("h-1", 80, name="http")]
    snap = diff_mod.snapshot(hosts, services)
    assert set(snap) == {"10.0.0.5"}
    assert snap["10.0.0.5"]["services"] == {(22, "tcp", "ssh"), (80, "tcp", "http")}


def test_diff_host_comparso_e_sparito():
    prev = diff_mod.snapshot([_host("a", "10.0.0.5")], [])
    cur = diff_mod.snapshot([_host("b", "10.0.0.6")], [])
    result = diff_mod.diff_snapshots(prev, cur)
    assert result["hosts_appeared"] == ["10.0.0.6"]
    assert result["hosts_disappeared"] == ["10.0.0.5"]


def test_diff_servizio_comparso_su_host_esistente():
    # Stesso host nelle due scansioni; nella seconda compare la porta 80.
    prev = diff_mod.snapshot([_host("a", "10.0.0.5")], [_service("a", 22)])
    cur = diff_mod.snapshot([_host("b", "10.0.0.5")],
                            [_service("b", 22), _service("b", 80, name="http")])
    result = diff_mod.diff_snapshots(prev, cur)
    assert result["services_appeared"] == [
        {"ip": "10.0.0.5", "port": 80, "protocol": "tcp", "name": "http"}]
    assert result["services_disappeared"] == []


def test_diff_host_riclassificato():
    prev = diff_mod.snapshot([_host("a", "10.0.0.5", models.HOST_UNKNOWN)], [])
    cur = diff_mod.snapshot([_host("b", "10.0.0.5", models.HOST_KNOWN)], [])
    result = diff_mod.diff_snapshots(prev, cur)
    assert result["hosts_reclassified"] == [
        {"ip": "10.0.0.5", "from": "unknown", "to": "known"}]


def test_diff_servizio_senza_nome_non_fa_fallire_l_ordinamento():
    # name None: l'ordinamento non deve sollevare confrontando None con stringhe.
    cur = diff_mod.snapshot(
        [_host("a", "10.0.0.5")],
        [_service("a", 22, name=None), _service("a", 80, name="http")])
    result = diff_mod.diff_snapshots({}, cur)
    assert len(result["services_appeared"]) == 2


# --- diff_for_scan (con database) --------------------------------------------

@pytest.fixture
def database(tmp_path):
    conf.load([])
    conf.CONF.set_override(
        "connection", f"sqlite:///{tmp_path / 'test.sqlite'}", group="database")
    db.reset()
    migration.upgrade()
    yield
    db.reset()


def _done_scan_with(project, hosts_spec):
    """Crea una scansione DONE con host (e servizi) e la restituisce.

    hosts_spec: lista di (ip, [porte]); ogni host è censito.
    """
    scan = db.create_scan(project, models.TRIGGER_MANUAL, status=models.SCAN_DONE)
    saved = db.save_hosts(scan.id, [
        {"ip_address": ip, "network_id": "net-1", "subnet_id": None,
         "neutron_port_id": None, "server_id": None, "server_name": None,
         "classification": models.HOST_KNOWN}
        for ip, _ports in hosts_spec])
    by_ip = {h.ip_address: h for h in saved}
    services = []
    for ip, ports in hosts_spec:
        for port in ports:
            services.append({"host_id": by_ip[ip].id, "port_number": port,
                             "protocol": "tcp", "name": "svc", "product": None,
                             "version": None, "view": models.VIEW_INTERNAL})
    db.save_services(services)
    return scan


def test_diff_for_scan_confronta_con_la_precedente(database):
    # Prima scansione: un host con ssh. Seconda: stesso host con ssh+http,
    # più un host nuovo.
    _done_scan_with("p-1", [("10.0.0.5", [22])])
    current = _done_scan_with("p-1", [("10.0.0.5", [22, 80]), ("10.0.0.9", [])])

    diff = diff_mod.diff_for_scan(current.id)
    assert diff["previous_scan_id"] is not None
    assert diff["hosts_appeared"] == ["10.0.0.9"]
    assert {(s["ip"], s["port"]) for s in diff["services_appeared"]} == {("10.0.0.5", 80)}


def test_diff_for_scan_prima_scansione_tutto_comparso(database):
    current = _done_scan_with("p-1", [("10.0.0.5", [22])])
    diff = diff_mod.diff_for_scan(current.id)
    assert diff["previous_scan_id"] is None
    assert diff["hosts_appeared"] == ["10.0.0.5"]
    assert len(diff["services_appeared"]) == 1
