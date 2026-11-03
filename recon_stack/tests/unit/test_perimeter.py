# Test del calcolo e del controllo del perimetro (scanner/perimeter.py).
#
# Niente OpenStack: una connessione finta restituisce le subnet e i floating IP
# del progetto, come farebbe Neutron.

import types

import pytest

from recon_stack import conf
from recon_stack.scanner import perimeter


def _obj(**kwargs):
    return types.SimpleNamespace(**kwargs)


class _Network:
    def __init__(self, subnets, networks=()):
        self._subnets = subnets
        self._networks = networks

    def networks(self, project_id=None):
        return list(self._networks)

    def subnets(self, project_id=None):
        return list(self._subnets)

    def ips(self, project_id=None):
        # I floating IP arrivano dall'inventario: Neutron non si rilegge.
        raise AssertionError("build non deve rileggere i floating IP da Neutron")


class FakeConnection:
    def __init__(self, subnets=(), networks=()):
        self.network = _Network(subnets, networks)


@pytest.fixture(autouse=True)
def _conf():
    # Serve CONF.scanner.max_perimeter_addresses in build().
    conf.load([])


def _demo_connection():
    return FakeConnection(
        subnets=[_obj(id="sub-1", network_id="net-1", cidr="10.10.10.0/24")])


DEMO_FLOATING_IPS = [_obj(floating_ip_address="172.24.4.10"),
                     _obj(floating_ip_address="172.24.4.11")]


def test_indirizzi_utilizzabili_escludono_rete_e_broadcast():
    # In una /24 il .0 (rete) e il .255 (broadcast) non si scansionano.
    p = perimeter.build(_demo_connection(), "progetto-1", DEMO_FLOATING_IPS)
    assert p.usable_internal_addresses == 254


def test_hosts_by_network_esclude_rete_e_broadcast():
    p = perimeter.build(_demo_connection(), "progetto-1", DEMO_FLOATING_IPS)
    hosts = p.hosts_by_network()["net-1"]
    assert "10.10.10.5" in hosts
    assert "10.10.10.0" not in hosts and "10.10.10.255" not in hosts
    assert len(hosts) == 254


def test_perimetro_troppo_grande_blocca_la_scansione():
    conf.CONF.set_override("max_perimeter_addresses", 100, group="scanner")
    conn = FakeConnection(
        subnets=[_obj(id="s", network_id="n", cidr="10.0.0.0/16")])
    with pytest.raises(perimeter.PerimeterTooLargeError):
        perimeter.build(conn, "progetto-1", [])


def test_una_16_supera_il_limite_predefinito():
    # Una /16 ha 65534 indirizzi utilizzabili: con il limite predefinito
    # deve essere rifiutata (come promette l'help dell'opzione).
    conn = FakeConnection(
        subnets=[_obj(id="s", network_id="n", cidr="10.0.0.0/16")])
    with pytest.raises(perimeter.PerimeterTooLargeError):
        perimeter.build(conn, "progetto-1", [])


def test_il_riepilogo_finisce_nel_log():
    p = perimeter.build(_demo_connection(), "progetto-1", DEMO_FLOATING_IPS)
    summary = p.as_dict()
    assert summary["internal_subnets"][0]["cidr"] == "10.10.10.0/24"
    assert summary["floating_ips"] == ["172.24.4.10", "172.24.4.11"]
    assert summary["usable_internal_addresses"] == 254


def test_perimetro_esclude_le_reti_router_external():
    # In DevStack `public` è router:external: non ha namespace ovnmeta-, quindi
    # le sue subnet non devono entrare nel perimetro.
    conn = FakeConnection(
        networks=[_obj(id="net-pub", is_router_external=True),
                  _obj(id="net-1", is_router_external=False)],
        subnets=[_obj(id="sub-pub", network_id="net-pub", cidr="172.24.4.0/24"),
                 _obj(id="sub-1", network_id="net-1", cidr="10.10.10.0/24")])
    p = perimeter.build(conn, "progetto-1", [])
    assert [s["subnet_id"] for s in p.internal_subnets] == ["sub-1"]
    assert list(p.hosts_by_network()) == ["net-1"]


def test_perimeter_non_rilegge_i_floating_ip():
    # conn.network.ips() solleva se chiamato: i floating IP passati dall'inventario
    # bastano, e finiscono comunque nel perimetro (anche quelli senza indirizzo
    # vengono ignorati).
    p = perimeter.build(
        _demo_connection(), "progetto-1",
        DEMO_FLOATING_IPS + [_obj(floating_ip_address=None)])
    assert p.floating_ips == {"172.24.4.10", "172.24.4.11"}
