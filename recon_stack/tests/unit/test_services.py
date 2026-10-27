# Test del service discovery (scanner/services.py): analisi dell'XML di nmap -sV
# e orchestrazione della scansione.
#
# Niente privilegi né OpenStack: diamo a parse_services un XML scritto a mano e,
# per discover_services, sostituiamo la funzione privilegiata con una che
# restituisce un XML preparato.

from recon_stack import conf
from recon_stack.scanner import services


# --- parse_services ----------------------------------------------------------

SERVICES_XML = """<?xml version="1.0"?>
<nmaprun>
  <host>
    <address addr="10.10.10.5" addrtype="ipv4"/>
    <ports>
      <port protocol="tcp" portid="22">
        <state state="open"/>
        <service name="ssh" product="OpenSSH" version="8.9p1"/>
      </port>
      <port protocol="tcp" portid="80">
        <state state="open"/>
        <service name="http" product="nginx" version="1.18.0"/>
      </port>
      <port protocol="tcp" portid="443">
        <state state="closed"/>
        <service name="https"/>
      </port>
    </ports>
  </host>
  <host>
    <address addr="10.10.10.50" addrtype="ipv4"/>
    <ports>
      <port protocol="tcp" portid="23">
        <state state="open"/>
        <service name="telnet"/>
      </port>
    </ports>
  </host>
</nmaprun>"""


def test_parse_estrae_i_servizi_per_ip():
    result = services.parse_services(SERVICES_XML)
    assert set(result) == {"10.10.10.5", "10.10.10.50"}
    web = sorted(result["10.10.10.5"], key=lambda s: s["port_number"])
    # Solo le porte aperte: la 443 "closed" è esclusa.
    assert [s["port_number"] for s in web] == [22, 80]
    assert web[0] == {"port_number": 22, "protocol": "tcp", "name": "ssh",
                      "product": "OpenSSH", "version": "8.9p1"}


def test_parse_servizio_senza_prodotto_ne_versione():
    # nmap non sempre riconosce prodotto e versione: gli attributi mancanti
    # devono risultare None, non far fallire il parsing.
    telnet = services.parse_services(SERVICES_XML)["10.10.10.50"][0]
    assert telnet["name"] == "telnet"
    assert telnet["product"] is None and telnet["version"] is None


def test_parse_host_senza_porte_aperte_non_compare():
    xml = """<nmaprun>
      <host>
        <address addr="10.10.10.1" addrtype="ipv4"/>
        <ports>
          <port protocol="tcp" portid="22"><state state="filtered"/></port>
        </ports>
      </host>
    </nmaprun>"""
    assert services.parse_services(xml) == {}


def test_parse_xml_senza_host():
    assert services.parse_services("<nmaprun></nmaprun>") == {}


# --- discover_services -------------------------------------------------------

def test_discover_senza_bersagli_non_scansiona(monkeypatch):
    # Senza host che rispondono non si entra nemmeno nel namespace.
    chiamata = []
    monkeypatch.setattr(services.priv_discovery, "service_scan_xml",
                        lambda *a, **k: chiamata.append(a) or "<nmaprun/>")
    assert services.discover_services("net-1", []) == {}
    assert chiamata == []


def test_discover_passa_il_namespace_e_la_profondita(monkeypatch):
    conf.load([])
    conf.CONF.set_override("network_driver", "ovn", group="scanner")
    conf.CONF.set_override("service_scan_scope", "comuni", group="scanner")
    visti = {}

    def finta(namespace, targets, scope):
        visti["namespace"] = namespace
        visti["targets"] = targets
        visti["scope"] = scope
        return SERVICES_XML

    monkeypatch.setattr(services.priv_discovery, "service_scan_xml", finta)
    result = services.discover_services("net-1", ["10.10.10.5", "10.10.10.50"])

    # Namespace calcolato dal driver (OVN) e profondità presa dalla config.
    assert visti["namespace"] == "ovnmeta-net-1"
    assert visti["targets"] == ["10.10.10.5", "10.10.10.50"]
    assert visti["scope"] == "comuni"
    assert set(result) == {"10.10.10.5", "10.10.10.50"}


# --- discover_external_services ----------------------------------------------

def test_discover_esterno_usa_la_namespace_radice(monkeypatch):
    conf.load([])
    conf.CONF.set_override("service_scan_scope", "top1000", group="scanner")
    visti = {}

    def finta(namespace, targets, scope):
        visti["namespace"] = namespace
        visti["targets"] = targets
        return SERVICES_XML

    monkeypatch.setattr(services.priv_discovery, "service_scan_xml", finta)
    result = services.discover_external_services(["172.24.4.10"])

    # La vista esterna non entra in nessuna namespace di progetto: namespace=None.
    assert visti["namespace"] is None
    assert visti["targets"] == ["172.24.4.10"]
    assert result  # ha analizzato l'XML


def test_discover_esterno_senza_floating_ip_non_scansiona(monkeypatch):
    chiamata = []
    monkeypatch.setattr(services.priv_discovery, "service_scan_xml",
                        lambda *a, **k: chiamata.append(a) or "<nmaprun/>")
    assert services.discover_external_services([]) == {}
    assert chiamata == []
