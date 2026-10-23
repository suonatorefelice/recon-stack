# Test dell'host discovery: analisi dell'XML di nmap e classificazione.
#
# Niente privilegi né OpenStack: diamo a parse_live_hosts un XML scritto a mano
# e a classify delle porte finte, e controlliamo le tre classificazioni.

import types

from recon_stack.scanner import discovery
from recon_stack.db import models


def _port(ip, port_id, network_id="net-1", subnet_id="sub-1",
          device_owner="compute:nova", device_id=None):
    return types.SimpleNamespace(
        ip_address=ip, port_id=port_id, network_id=network_id,
        subnet_id=subnet_id, device_owner=device_owner, device_id=device_id)


# --- parse_live_hosts --------------------------------------------------------

NMAP_XML = """<?xml version="1.0"?>
<nmaprun>
  <host>
    <status state="up"/>
    <address addr="10.10.10.5" addrtype="ipv4"/>
  </host>
  <host>
    <status state="down"/>
    <address addr="10.10.10.6" addrtype="ipv4"/>
  </host>
  <host>
    <status state="up"/>
    <address addr="10.10.10.7" addrtype="ipv4"/>
  </host>
</nmaprun>"""


def test_parse_prende_solo_gli_host_up():
    assert discovery.parse_live_hosts(NMAP_XML) == {"10.10.10.5", "10.10.10.7"}


def test_parse_xml_senza_host():
    assert discovery.parse_live_hosts("<nmaprun></nmaprun>") == set()


# --- classify ----------------------------------------------------------------

def test_una_vm_che_risponde_e_censita():
    ports = [_port("10.10.10.5", "port-vm", device_id="vm-1")]
    hosts = discovery.classify("net-1", {"10.10.10.5"}, ports,
                               servers_by_id={"vm-1": "web"})
    assert len(hosts) == 1
    h = hosts[0]
    assert h["classification"] == models.HOST_KNOWN
    assert h["neutron_port_id"] == "port-vm"
    assert h["server_id"] == "vm-1"
    assert h["server_name"] == "web"


def test_un_ip_che_risponde_senza_porta_e_sconosciuto():
    # Nessuna porta spiega 10.10.10.99: host sconosciuto, da indagare.
    hosts = discovery.classify("net-1", {"10.10.10.99"}, ports=[])
    assert len(hosts) == 1
    assert hosts[0]["classification"] == models.HOST_UNKNOWN
    assert hosts[0]["neutron_port_id"] is None
    assert hosts[0]["network_id"] == "net-1"


def test_una_porta_che_non_risponde_e_assente():
    # C'è la porta (quindi un IP riservato) ma nessuno risponde: assente.
    ports = [_port("10.10.10.5", "port-vm", device_id="vm-1")]
    hosts = discovery.classify("net-1", set(), ports)
    assert len(hosts) == 1
    assert hosts[0]["classification"] == models.HOST_ABSENT
    assert hosts[0]["neutron_port_id"] == "port-vm"


def test_una_porta_di_router_non_viene_attribuita_a_una_vm():
    # device_owner di un router: la porta risponde ed è censita, ma senza VM.
    ports = [_port("10.10.10.1", "port-router",
                   device_owner="network:router_interface", device_id="router-1")]
    hosts = discovery.classify("net-1", {"10.10.10.1"}, ports)
    assert hosts[0]["classification"] == models.HOST_KNOWN
    assert hosts[0]["server_id"] is None
    assert hosts[0]["server_name"] is None


def test_scenario_misto():
    ports = [
        _port("10.10.10.5", "port-vm1", device_id="vm-1"),   # risponde -> censito
        _port("10.10.10.6", "port-vm2", device_id="vm-2"),   # non risponde -> assente
    ]
    responding = {"10.10.10.5", "10.10.10.200"}              # .200 non ha porta -> sconosciuto
    hosts = discovery.classify("net-1", responding, ports,
                               servers_by_id={"vm-1": "web", "vm-2": "db"})
    by_class = {}
    for h in hosts:
        by_class.setdefault(h["classification"], []).append(h["ip_address"])
    assert by_class[models.HOST_KNOWN] == ["10.10.10.5"]
    assert by_class[models.HOST_UNKNOWN] == ["10.10.10.200"]
    assert by_class[models.HOST_ABSENT] == ["10.10.10.6"]
