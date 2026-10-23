# Test dei nomi delle network namespace (scanner/namespaces.py).

import pytest

from recon_stack import conf
from recon_stack.scanner import namespaces


def test_ovn_usa_ovnmeta():
    assert namespaces.internal_namespace("rete-1", "ovn") == "ovnmeta-rete-1"


def test_ovs_usa_qdhcp():
    assert namespaces.internal_namespace("rete-1", "ovs") == "qdhcp-rete-1"


def test_usa_il_driver_della_configurazione():
    conf.load([])
    conf.CONF.set_override("network_driver", "ovs", group="scanner")
    assert namespaces.internal_namespace("rete-9") == "qdhcp-rete-9"


def test_driver_sconosciuto_e_un_errore():
    with pytest.raises(ValueError):
        namespaces.internal_namespace("rete-1", "boh")
