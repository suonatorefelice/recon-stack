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
    def __init__(self, ports, floating_ips, security_groups=(),
                 security_group_rules=()):
        self._ports = ports
        self._floating_ips = floating_ips
        self._security_groups = security_groups
        self._security_group_rules = security_group_rules

    def ports(self, project_id=None):
        return list(self._ports)

    def ips(self, project_id=None):
        return list(self._floating_ips)

    def security_groups(self, project_id=None):
        return list(self._security_groups)

    def security_group_rules(self, project_id=None):
        return list(self._security_group_rules)


class _Identity:
    def __init__(self, project):
        self._project = project

    def find_project(self, name_or_id, ignore_missing=True):
        return self._project


class FakeConnection:
    def __init__(self, servers=(), ports=(), floating_ips=(),
                 security_groups=(), security_group_rules=(), project=None):
        self.compute = _Compute(servers)
        self.network = _Network(ports, floating_ips, security_groups,
                                security_group_rules)
        # Per il comando recon-stack-inventory, che risolve il progetto.
        self.identity = _Identity(
            project or _obj(id="progetto-1", name="recon-demo"))


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


def test_colleziona_security_group_e_regole(db):
    scan = api.create_scan("progetto-1", "manual")
    conn = FakeConnection(
        ports=[
            # La porta della VM riporta i suoi security group.
            _obj(id="port-vm", network_id="net-1",
                 mac_address="fa:16:3e:00:00:01",
                 device_owner="compute:nova", device_id="vm-1",
                 security_group_ids=["sg-1"],
                 fixed_ips=[{"ip_address": "10.0.0.5", "subnet_id": "sub-1"}]),
        ],
        security_groups=[_obj(id="sg-1", name="recon-demo-sg")],
        security_group_rules=[
            # Regola in ingresso: TCP 22 da qualunque indirizzo.
            _obj(id="rule-ssh", security_group_id="sg-1", direction="ingress",
                 ether_type="IPv4", protocol="tcp", port_range_min=22,
                 port_range_max=22, remote_ip_prefix="0.0.0.0/0",
                 remote_group_id=None),
            # Regola senza porte né protocollo (uscita libera verso tutto).
            _obj(id="rule-egress", security_group_id="sg-1", direction="egress",
                 ether_type="IPv4", protocol=None, port_range_min=None,
                 port_range_max=None, remote_ip_prefix=None, remote_group_id=None),
        ],
    )

    inventory.collect_and_save(conn, "progetto-1", scan.id)

    saved = api.get_inventory(scan.id)
    assert len(saved["security_groups"]) == 1
    assert saved["security_groups"][0].name == "recon-demo-sg"

    rules = {r.rule_id: r for r in saved["security_group_rules"]}
    assert len(rules) == 2
    ssh = rules["rule-ssh"]
    assert ssh.direction == "ingress"
    assert ssh.protocol == "tcp"
    assert ssh.port_range_min == 22 and ssh.port_range_max == 22
    assert ssh.remote_ip_prefix == "0.0.0.0/0"
    assert ssh.ethertype == "IPv4"
    # La porta conserva i suoi security group come lista JSON.
    import json
    vm_port = next(p for p in saved["ports"] if p.port_id == "port-vm")
    assert json.loads(vm_port.security_group_ids) == ["sg-1"]


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
    assert saved == {"servers": [], "ports": [], "floating_ips": [],
                     "security_groups": [], "security_group_rules": []}


def test_comando_inventory_crea_una_scansione_e_salva(db, monkeypatch, capsys):
    # Il comando usa cloud.connect() per aprire la connessione: la sostituiamo
    # con quella finta, così il test non tocca OpenStack.
    from recon_stack.cmd import inventory as cmd_inventory

    conn = FakeConnection(
        servers=[_obj(id="vm-1", name="web", status="ACTIVE")],
        project=_obj(id="progetto-1", name="recon-demo"),
    )
    monkeypatch.setattr(cmd_inventory.cloud, "connect", lambda: conn)

    exit_code = cmd_inventory.main(["--project", "recon-demo"])
    assert exit_code == 0

    # Ha creato esattamente una scansione per quel progetto, con l'inventario.
    scans = api.list_scans(project_id="progetto-1")
    assert len(scans) == 1
    saved = api.get_inventory(scans[0].id)
    assert len(saved["servers"]) == 1
    # E ha stampato un riepilogo leggibile.
    assert "web" in capsys.readouterr().out


def test_comando_inventory_progetto_inesistente(db, monkeypatch):
    from recon_stack.cmd import inventory as cmd_inventory

    conn = FakeConnection(project=None)
    # find_project che restituisce None: progetto non trovato.
    conn.identity = _Identity(None)
    monkeypatch.setattr(cmd_inventory.cloud, "connect", lambda: conn)

    assert cmd_inventory.main(["--project", "non-esiste"]) == 1
    assert api.list_scans() == []
