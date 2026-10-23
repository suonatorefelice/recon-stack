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
    def __init__(self, subnets, floating_ips):
        self._subnets = subnets
        self._floating_ips = floating_ips

    def subnets(self, project_id=None):
        return list(self._subnets)

    def ips(self, project_id=None):
        return list(self._floating_ips)


class FakeConnection:
    def __init__(self, subnets=(), floating_ips=()):
        self.network = _Network(subnets, floating_ips)


@pytest.fixture(autouse=True)
def _conf():
    # Serve CONF.scanner.max_perimeter_addresses in build().
    conf.load([])


def _demo_connection():
    return FakeConnection(
        subnets=[_obj(id="sub-1", network_id="net-1", cidr="10.10.10.0/24")],
        floating_ips=[_obj(floating_ip_address="172.24.4.10"),
                      _obj(floating_ip_address="172.24.4.11")],
    )


def test_un_ip_della_subnet_e_dentro():
    p = perimeter.build(_demo_connection(), "progetto-1")
    assert p.contains("10.10.10.5") is True


def test_un_floating_ip_del_progetto_e_dentro():
    p = perimeter.build(_demo_connection(), "progetto-1")
    assert p.contains("172.24.4.10") is True


def test_rete_e_broadcast_non_sono_utilizzabili():
    # In una /24 il .0 (rete) e il .255 (broadcast) non si scansionano.
    p = perimeter.build(_demo_connection(), "progetto-1")
    assert p.contains("10.10.10.0") is False
    assert p.contains("10.10.10.255") is False
    assert p.usable_internal_addresses == 254


def test_un_ip_di_un_altro_progetto_e_fuori():
    # 10.20.20.5 non appartiene ad alcuna subnet del progetto: fuori perimetro.
    p = perimeter.build(_demo_connection(), "progetto-1")
    assert p.contains("10.20.20.5") is False


def test_check_rifiuta_i_bersagli_fuori_perimetro():
    p = perimeter.build(_demo_connection(), "progetto-1")
    # Tutti dentro: non solleva niente.
    p.check(["10.10.10.5", "172.24.4.10"])
    # Uno fuori: solleva PerimeterError con l'elenco degli indirizzi incriminati.
    with pytest.raises(perimeter.PerimeterError) as exc:
        p.check(["10.10.10.5", "10.20.20.5", "8.8.8.8"])
    assert exc.value.targets == ["10.20.20.5", "8.8.8.8"]


def test_perimetro_troppo_grande_blocca_la_scansione():
    conf.CONF.set_override("max_perimeter_addresses", 100, group="scanner")
    conn = FakeConnection(
        subnets=[_obj(id="s", network_id="n", cidr="10.0.0.0/16")])
    with pytest.raises(perimeter.PerimeterTooLargeError):
        perimeter.build(conn, "progetto-1")


def test_il_riepilogo_finisce_nel_log():
    p = perimeter.build(_demo_connection(), "progetto-1")
    summary = p.as_dict()
    assert summary["internal_subnets"][0]["cidr"] == "10.10.10.0/24"
    assert summary["floating_ips"] == ["172.24.4.10", "172.24.4.11"]
    assert summary["usable_internal_addresses"] == 254
