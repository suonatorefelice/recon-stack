# Test della raccolta dell'inventario (recon_stack/scanner/inventory.py).
#
# Non serve un OpenStack vero: costruiamo una connessione finta (FakeConnection)
# che restituisce qualche VM, porta e floating IP preparati a mano, come farebbe
# openstacksdk. Così proviamo che inventory.collect legga i campi giusti e che
# i dati escano in memoria (namedtuple) con la forma attesa.

import types

from recon_stack.scanner import inventory


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
        # Risolve il progetto, come farebbe la connessione vera.
        self.identity = _Identity(
            project or _obj(id="progetto-1", name="recon-demo"))


# --- Test --------------------------------------------------------------------

def test_colleziona_vm_porte_e_floating_ip():
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

    servers, ports, fips, _rules = inventory.collect(conn, "progetto-1", "scan-1")

    # Le VM servono per dare un nome agli host.
    assert len(servers) == 1
    assert servers[0].server_id == "vm-1"
    assert servers[0].name == "web"
    assert servers[0].status == "ACTIVE"

    assert len(ports) == 2
    vm_port = next(p for p in ports if p.port_id == "port-vm")
    assert vm_port.ip_address == "10.0.0.5"
    assert vm_port.subnet_id == "sub-1"
    assert vm_port.device_owner == "compute:nova"
    assert vm_port.device_id == "vm-1"

    assert len(fips) == 1
    assert fips[0].floating_ip_address == "172.24.4.10"
    assert fips[0].fixed_ip_address == "10.0.0.5"
    assert fips[0].port_id == "port-vm"


def test_colleziona_security_group_e_regole():
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

    _servers, ports, _fips, rules = inventory.collect(conn, "progetto-1", "scan-1")

    assert len(rules) == 2
    ssh = next(r for r in rules if r.protocol == "tcp")
    assert ssh.direction == "ingress"
    assert ssh.protocol == "tcp"
    assert ssh.port_range_min == 22 and ssh.port_range_max == 22
    assert ssh.remote_ip_prefix == "0.0.0.0/0"
    assert ssh.security_group_id == "sg-1"
    # La porta conserva i suoi security group come tupla di id.
    vm_port = next(p for p in ports if p.port_id == "port-vm")
    assert vm_port.security_group_ids == ("sg-1",)


def test_una_porta_con_piu_ip_diventa_piu_righe():
    conn = FakeConnection(ports=[
        _obj(id="port-2", network_id="net-1", mac_address="fa:16:3e:00:00:03",
             device_owner="compute:nova", device_id="vm-2",
             fixed_ips=[
                 {"ip_address": "10.0.0.6", "subnet_id": "sub-1"},
                 {"ip_address": "10.0.1.6", "subnet_id": "sub-2"},
             ]),
    ])

    _servers, ports, _fips, _rules = inventory.collect(conn, "progetto-1", "scan-1")

    assert len(ports) == 2
    assert {p.ip_address for p in ports} == {"10.0.0.6", "10.0.1.6"}
    assert all(p.port_id == "port-2" for p in ports)


def test_inventario_vuoto():
    assert inventory.collect(FakeConnection(), "progetto-1", "scan-1") == (
        [], [], [], [])
