# Test della raccolta dell'inventario (recon_stack/scanner/inventory.py).
#
# Non serve un OpenStack vero: costruiamo una connessione finta (FakeConnection)
# che restituisce qualche VM, porta e floating IP preparati a mano, come farebbe
# openstacksdk. Così proviamo che inventory.collect legga i campi giusti e che
# i dati finiscano nel database con la forma attesa.

import types

import pytest

from recon_stack import conf
from recon_stack.db import api
from recon_stack.db import migration
from recon_stack.scanner import inventory


@pytest.fixture
def db(tmp_path):
    """Database nuovo, con tutte le migrazioni applicate (come in test_db.py)."""
    conf.load([])
    conf.CONF.set_override(
        "connection", f"sqlite:///{tmp_path / 'test.sqlite'}", group="database")
    api.reset()
    migration.upgrade()
    yield
    api.reset()


# --- Connessione OpenStack finta --------------------------------------------

def _obj(**kwargs):
    """Un oggetto con gli attributi indicati, come quelli di openstacksdk."""
    return types.SimpleNamespace(**kwargs)


class _Compute:
    def __init__(self, servers):
        self._servers = servers

    def servers(self, all_projects=False, project_id=None):
        # La connessione finta ignora i filtri: restituisce sempre la stessa
        # lista. Il test verifica che inventory.collect li passi senza errori.
        return list(self._servers)


class _Network:
    def __init__(self, ports, floating_ips):
        self._ports = ports
        self._floating_ips = floating_ips

    def ports(self, project_id=None):
        return list(self._ports)

    def ips(self, project_id=None):
        return list(self._floating_ips)


class FakeConnection:
    def __init__(self, servers=(), ports=(), floating_ips=()):
        self.compute = _Compute(servers)
        self.network = _Network(ports, floating_ips)


# --- Test --------------------------------------------------------------------

def test_colleziona_vm_porte_e_floating_ip(db):
    scan = api.create_scan("progetto-1", "manual")
    conn = FakeConnection(
        servers=[_obj(id="vm-1", name="web", status="ACTIVE")],
        ports=[
            # Porta di una VM con un IP fisso.
            _obj(id="port-vm", network_id="net-1",
                 mac_address="fa:16:3e:00:00:01",
                 device_owner="compute:nova", device_id="vm-1",
                 fixed_ips=[{"ip_address": "10.0.0.5", "subnet_id": "sub-1"}]),
            # Porta di un router, senza VM.
            _obj(id="port-router", network_id="net-1",
                 mac_address="fa:16:3e:00:00:02",
                 device_owner="network:router_interface", device_id="router-1",
                 fixed_ips=[{"ip_address": "10.0.0.1", "subnet_id": "sub-1"}]),
        ],
        floating_ips=[
            _obj(id="fip-1", floating_ip_address="172.24.4.10",
                 fixed_ip_address="10.0.0.5", port_id="port-vm"),
        ],
    )

    inventory.collect_and_save(conn, "progetto-1", scan.id)

    saved = api.get_inventory(scan.id)
    assert len(saved["servers"]) == 1
    assert saved["servers"][0].server_id == "vm-1"
    assert saved["servers"][0].status == "ACTIVE"

    assert len(saved["ports"]) == 2
    vm_port = next(p for p in saved["ports"] if p.port_id == "port-vm")
    assert vm_port.ip_address == "10.0.0.5"
    assert vm_port.subnet_id == "sub-1"
    assert vm_port.device_owner == "compute:nova"
    assert vm_port.device_id == "vm-1"

    assert len(saved["floating_ips"]) == 1
    assert saved["floating_ips"][0].floating_ip_address == "172.24.4.10"
    assert saved["floating_ips"][0].fixed_ip_address == "10.0.0.5"


def test_una_porta_con_piu_ip_diventa_piu_righe(db):
    scan = api.create_scan("progetto-1", "manual")
    conn = FakeConnection(ports=[
        _obj(id="port-2", network_id="net-1", mac_address="fa:16:3e:00:00:03",
             device_owner="compute:nova", device_id="vm-2",
             fixed_ips=[
                 {"ip_address": "10.0.0.6", "subnet_id": "sub-1"},
                 {"ip_address": "10.0.1.6", "subnet_id": "sub-2"},
             ]),
    ])

    inventory.collect_and_save(conn, "progetto-1", scan.id)

    saved = api.get_inventory(scan.id)
    assert len(saved["ports"]) == 2
    assert {p.ip_address for p in saved["ports"]} == {"10.0.0.6", "10.0.1.6"}
    assert all(p.port_id == "port-2" for p in saved["ports"])


def test_inventario_vuoto(db):
    scan = api.create_scan("progetto-1", "manual")
    inventory.collect_and_save(FakeConnection(), "progetto-1", scan.id)
    saved = api.get_inventory(scan.id)
    assert saved == {"servers": [], "ports": [], "floating_ips": []}
