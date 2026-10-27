# Test dell'esecuzione di una scansione (scanner/scan.py) e del comando
# recon-stack-scan.
#
# Non servono né root né nmap né OpenStack: una connessione finta fa da Neutron
# e Nova, e sostituiamo la funzione privilegiata (che eseguirebbe nmap nel
# namespace) con una che restituisce un XML preparato a mano.

import json
import types

import pytest

from recon_stack import conf
from recon_stack.db import api as db
from recon_stack.db import migration
from recon_stack.db import models
from recon_stack.scanner import discovery
from recon_stack.scanner import scan as scan_mod


@pytest.fixture
def database(tmp_path):
    conf.load([])
    conf.CONF.set_override(
        "connection", f"sqlite:///{tmp_path / 'test.sqlite'}", group="database")
    api_reset_and_migrate()
    yield
    db.reset()


def api_reset_and_migrate():
    db.reset()
    migration.upgrade()


def _obj(**kwargs):
    return types.SimpleNamespace(**kwargs)


class _Compute:
    def __init__(self, servers):
        self._servers = servers

    def servers(self, all_projects=False, project_id=None):
        return list(self._servers)


class _Network:
    def __init__(self, subnets, ports, floating_ips,
                 security_groups=(), security_group_rules=()):
        self._subnets = subnets
        self._ports = ports
        self._floating_ips = floating_ips
        self._security_groups = security_groups
        self._security_group_rules = security_group_rules

    def subnets(self, project_id=None):
        return list(self._subnets)

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
    def __init__(self):
        self.compute = _Compute([
            _obj(id="vm-1", name="web", status="ACTIVE"),
            _obj(id="vm-2", name="db", status="ACTIVE"),
        ])
        self.network = _Network(
            subnets=[_obj(id="sub-1", network_id="net-1", cidr="10.10.10.0/24")],
            ports=[
                _port("10.10.10.5", "port-vm1", device_id="vm-1"),   # risponde
                _port("10.10.10.6", "port-vm2", device_id="vm-2"),   # non risponde
                _port("10.10.10.1", "port-router",
                      device_owner="network:router_interface", device_id="r-1"),
            ],
            floating_ips=[_obj(floating_ip_address="172.24.4.10",
                               fixed_ip_address="10.10.10.5", id="fip-1",
                               port_id="port-vm1")],
        )
        self.identity = _Identity(_obj(id="progetto-1", name="recon-demo"))


def _port(ip, port_id, device_owner="compute:nova", device_id=None):
    # Forma di una porta Neutron (quella che legge inventory.collect):
    # un elenco fixed_ips con indirizzo e subnet.
    return _obj(id=port_id, network_id="net-1",
                mac_address="fa:16:3e:00:00:00",
                device_owner=device_owner, device_id=device_id,
                fixed_ips=[{"ip_address": ip, "subnet_id": "sub-1"}])


# XML di nmap (host discovery): rispondono la VM web (.5), il router (.1) e un
# intruso (.50). La VM db (.6) non risponde.
FAKE_XML = """<nmaprun>
  <host><status state="up"/><address addr="10.10.10.5" addrtype="ipv4"/></host>
  <host><status state="up"/><address addr="10.10.10.1" addrtype="ipv4"/></host>
  <host><status state="up"/><address addr="10.10.10.50" addrtype="ipv4"/></host>
</nmaprun>"""

# XML di nmap (vista esterna): sul floating IP .10 risponde solo ssh. Serve a
# provare che la scansione esterna aggancia i servizi all'host dell'IP privato.
FAKE_EXTERNAL_XML = """<nmaprun>
  <host>
    <address addr="172.24.4.10" addrtype="ipv4"/>
    <ports>
      <port protocol="tcp" portid="22">
        <state state="open"/>
        <service name="ssh" product="OpenSSH" version="8.9p1"/>
      </port>
    </ports>
  </host>
</nmaprun>"""

# XML di nmap (service discovery): la VM web (.5) espone ssh e http; l'intruso
# (.50) espone una porta ssh. Il router (.1) non ha porte aperte.
FAKE_SERVICES_XML = """<nmaprun>
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
    </ports>
  </host>
  <host>
    <address addr="10.10.10.1" addrtype="ipv4"/>
    <ports></ports>
  </host>
  <host>
    <address addr="10.10.10.50" addrtype="ipv4"/>
    <ports>
      <port protocol="tcp" portid="22">
        <state state="open"/>
        <service name="ssh"/>
      </port>
    </ports>
  </host>
</nmaprun>"""


@pytest.fixture
def no_privsep(monkeypatch):
    """Sostituisce le funzioni privilegiate con dati finti che non toccano la rete.

    priv_discovery è lo stesso modulo visto sia da scanner/discovery.py sia da
    scanner/services.py, quindi basta sostituirvi le due funzioni una volta.
    """
    monkeypatch.setattr(discovery.priv_discovery, "live_hosts_xml",
                        lambda namespace, targets: FAKE_XML)

    # service_scan_xml serve sia alla vista interna (namespace della rete) sia a
    # quella esterna (namespace=None, sui floating IP): distinguiamo dai target.
    def finta_service_scan(namespace, targets, scope):
        if namespace is None:
            return FAKE_EXTERNAL_XML
        return FAKE_SERVICES_XML

    monkeypatch.setattr(discovery.priv_discovery, "service_scan_xml",
                        finta_service_scan)


# --- run_scan ----------------------------------------------------------------

def test_scansione_completa_classifica_gli_host(database, no_privsep):
    scan = db.create_scan("progetto-1", models.TRIGGER_MANUAL)
    result = scan_mod.run_scan(FakeConnection(), scan.id)

    assert result.status == models.SCAN_DONE
    assert result.started_at is not None and result.finished_at is not None

    known = db.get_hosts(scan.id, models.HOST_KNOWN)
    unknown = db.get_hosts(scan.id, models.HOST_UNKNOWN)
    absent = db.get_hosts(scan.id, models.HOST_ABSENT)
    assert {h.ip_address for h in known} == {"10.10.10.1", "10.10.10.5"}
    assert {h.ip_address for h in unknown} == {"10.10.10.50"}
    assert {h.ip_address for h in absent} == {"10.10.10.6"}
    # La VM censita porta il suo nome.
    web = next(h for h in known if h.ip_address == "10.10.10.5")
    assert web.server_name == "web"


def test_la_scansione_trova_i_servizi_sugli_host_che_rispondono(database, no_privsep):
    scan = db.create_scan("progetto-1", models.TRIGGER_MANUAL)
    scan_mod.run_scan(FakeConnection(), scan.id)

    # Collego i servizi trovati all'IP del loro host per poterli controllare.
    hosts_by_id = {h.id: h for h in db.get_hosts(scan.id)}
    services_by_ip = {}
    for svc in db.get_services(scan.id):
        services_by_ip.setdefault(hosts_by_id[svc.host_id].ip_address, []).append(svc)

    # La VM web (.5) espone ssh e http dall'interno, con prodotto e versione.
    web = sorted([s for s in services_by_ip["10.10.10.5"]
                  if s.view == models.VIEW_INTERNAL], key=lambda s: s.port_number)
    assert [(s.port_number, s.name) for s in web] == [(22, "ssh"), (80, "http")]
    assert web[0].product == "OpenSSH" and web[0].version == "8.9p1"
    # Anche l'host sconosciuto (.50) viene interrogato: espone ssh senza versione.
    intruso = [s for s in services_by_ip["10.10.10.50"]
               if s.view == models.VIEW_INTERNAL]
    assert [(s.port_number, s.name) for s in intruso] == [(22, "ssh")]
    assert intruso[0].product is None and intruso[0].version is None
    # Il router (.1) non ha porte aperte: nessun servizio.
    assert "10.10.10.1" not in services_by_ip


def test_la_scansione_vede_i_servizi_esterni_sul_floating_ip(database, no_privsep):
    scan = db.create_scan("progetto-1", models.TRIGGER_MANUAL)
    scan_mod.run_scan(FakeConnection(), scan.id)

    hosts_by_id = {h.id: h for h in db.get_hosts(scan.id)}
    external = [s for s in db.get_services(scan.id)
                if s.view == models.VIEW_EXTERNAL]
    # Il floating IP 172.24.4.10 inoltra verso 10.10.10.5 (la VM web): il
    # servizio ssh visto da fuori si aggancia a quell'host, con vista esterna.
    assert len(external) == 1
    assert hosts_by_id[external[0].host_id].ip_address == "10.10.10.5"
    assert (external[0].port_number, external[0].name) == (22, "ssh")


def test_la_scansione_produce_segnalazioni_di_esposizione(database, no_privsep):
    scan = db.create_scan("progetto-1", models.TRIGGER_MANUAL)
    scan_mod.run_scan(FakeConnection(), scan.id)

    findings = db.get_findings(scan.id)
    tipi = {f.finding_type for f in findings}
    # L'host sconosciuto (.50) con ssh aperto deve essere segnalato.
    assert models.FINDING_UNKNOWN_EXPOSED in tipi
    # Senza security group nella scansione finta, i servizi dell'host censito
    # risultano "latenti" (nessuna regola li prevede).
    assert models.FINDING_LATENT_SERVICE in tipi


def test_la_scansione_scrive_il_perimetro_nel_log(database, no_privsep):
    scan = db.create_scan("progetto-1", models.TRIGGER_MANUAL)
    scan_mod.run_scan(FakeConnection(), scan.id)
    saved = db.get_scan(scan.id)
    perimeter = json.loads(saved.perimeter)
    assert perimeter["internal_subnets"][0]["cidr"] == "10.10.10.0/24"
    assert perimeter["floating_ips"] == ["172.24.4.10"]


def test_una_scansione_fallita_viene_registrata(database, no_privsep):
    # Perimetro troppo grande: la build fallisce, la scansione risulta FAILED.
    conf.CONF.set_override("max_perimeter_addresses", 10, group="scanner")
    scan = db.create_scan("progetto-1", models.TRIGGER_MANUAL)
    with pytest.raises(Exception):
        scan_mod.run_scan(FakeConnection(), scan.id)
    saved = db.get_scan(scan.id)
    assert saved.status == models.SCAN_FAILED
    assert saved.fault


# --- comando -----------------------------------------------------------------

def test_comando_scan(database, no_privsep, monkeypatch, capsys):
    from recon_stack.cmd import scan as cmd_scan
    monkeypatch.setattr(cmd_scan.cloud, "connect", lambda: FakeConnection())

    assert cmd_scan.main(["--project", "recon-demo"]) == 0
    out = capsys.readouterr().out
    assert "censiti: 2" in out
    assert "sconosciuti: 1" in out
    assert "assenti: 1" in out
