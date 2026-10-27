# Test del motore di esposizione (scanner/exposure.py).
#
# build_findings non tocca il database: costruiamo host, servizi e inventario a
# mano (SimpleNamespace, come gli oggetti del database) e controlliamo quali
# segnalazioni produce. Un test finale prova il giro completo sul database
# (compute_and_save + get_findings), compreso l'ordinamento per gravità.

import json
import types

import pytest

from recon_stack import conf
from recon_stack.db import api
from recon_stack.db import migration
from recon_stack.db import models
from recon_stack.scanner import exposure


def _obj(**kwargs):
    return types.SimpleNamespace(**kwargs)


def _host(host_id, ip, classification=models.HOST_KNOWN):
    return _obj(id=host_id, ip_address=ip, classification=classification)


def _service(host_id, port, name="ssh", protocol="tcp", view=models.VIEW_INTERNAL):
    return _obj(host_id=host_id, port_number=port, protocol=protocol,
                name=name, view=view)


def _port(ip, sg_ids):
    return _obj(ip_address=ip, security_group_ids=json.dumps(sg_ids))


def _rule(sg_id, port_min=None, port_max=None, protocol="tcp",
          direction="ingress", remote="0.0.0.0/0", remote_group=None):
    return _obj(security_group_id=sg_id, direction=direction, protocol=protocol,
                port_range_min=port_min, port_range_max=port_max,
                remote_ip_prefix=remote, remote_group_id=remote_group)


def _inventory(ports=(), rules=(), floating_ips=()):
    return {"ports": list(ports), "security_group_rules": list(rules),
            "floating_ips": list(floating_ips)}


def _types(findings):
    return {f["finding_type"] for f in findings}


# --- Esposizione eccessiva / servizio latente / regola inutile ---------------

def test_servizio_aperto_a_tutti_e_esposizione_eccessiva():
    host = _host("h1", "10.0.0.5")
    services = [_service("h1", 22)]
    inv = _inventory(
        ports=[_port("10.0.0.5", ["sg-1"])],
        rules=[_rule("sg-1", 22, 22, remote="0.0.0.0/0")])

    findings = exposure.build_findings([host], services, inv)
    over = [f for f in findings if f["finding_type"] == models.FINDING_OVEREXPOSED]
    assert len(over) == 1
    assert over[0]["severity"] == models.SEVERITY_HIGH
    assert over[0]["port_number"] == 22
    assert "0.0.0.0/0" in over[0]["message"]


def test_servizio_aperto_solo_a_una_rete_non_e_esposizione_eccessiva():
    host = _host("h1", "10.0.0.5")
    services = [_service("h1", 22)]
    inv = _inventory(
        ports=[_port("10.0.0.5", ["sg-1"])],
        rules=[_rule("sg-1", 22, 22, remote="10.0.0.0/24")])

    findings = exposure.build_findings([host], services, inv)
    # La porta è coperta da una regola ristretta: né latente né esposto a tutti.
    assert models.FINDING_OVEREXPOSED not in _types(findings)
    assert models.FINDING_LATENT_SERVICE not in _types(findings)


def test_servizio_senza_regola_e_latente():
    host = _host("h1", "10.0.0.5")
    services = [_service("h1", 3306, name="mysql")]
    inv = _inventory(ports=[_port("10.0.0.5", ["sg-1"])],
                     rules=[_rule("sg-1", 22, 22)])  # apre solo la 22

    findings = exposure.build_findings([host], services, inv)
    latent = [f for f in findings
              if f["finding_type"] == models.FINDING_LATENT_SERVICE]
    assert len(latent) == 1
    assert latent[0]["port_number"] == 3306
    assert latent[0]["severity"] == models.SEVERITY_MEDIUM


def test_regola_senza_servizio_e_inutile():
    host = _host("h1", "10.0.0.5")
    services = [_service("h1", 22)]  # in ascolto solo ssh
    inv = _inventory(
        ports=[_port("10.0.0.5", ["sg-1"])],
        rules=[_rule("sg-1", 22, 22), _rule("sg-1", 3306, 3306)])  # 3306 inutile

    findings = exposure.build_findings([host], services, inv)
    useless = [f for f in findings
               if f["finding_type"] == models.FINDING_USELESS_RULE]
    assert len(useless) == 1
    assert useless[0]["port_number"] == 3306
    assert useless[0]["severity"] == models.SEVERITY_LOW


def test_regola_icmp_o_qualunque_porta_non_e_mai_inutile():
    host = _host("h1", "10.0.0.5")
    services = [_service("h1", 22)]
    inv = _inventory(
        ports=[_port("10.0.0.5", ["sg-1"])],
        rules=[_rule("sg-1", protocol="icmp", port_min=None, port_max=None),
               _rule("sg-1", protocol="tcp", port_min=None, port_max=None)])

    findings = exposure.build_findings([host], services, inv)
    assert models.FINDING_USELESS_RULE not in _types(findings)


# --- Host non censito --------------------------------------------------------

def test_host_sconosciuto_con_porte_aperte():
    host = _host("h1", "10.0.0.50", classification=models.HOST_UNKNOWN)
    services = [_service("h1", 22)]
    findings = exposure.build_findings([host], services, _inventory())
    unknown = [f for f in findings
               if f["finding_type"] == models.FINDING_UNKNOWN_EXPOSED]
    assert len(unknown) == 1
    assert unknown[0]["severity"] == models.SEVERITY_HIGH
    assert unknown[0]["ip_address"] == "10.0.0.50"


def test_host_sconosciuto_senza_porte_non_segnala():
    host = _host("h1", "10.0.0.50", classification=models.HOST_UNKNOWN)
    findings = exposure.build_findings([host], [], _inventory())
    assert findings == []


def test_host_assente_non_genera_segnalazioni_di_regole():
    host = _host("h1", "10.0.0.6", classification=models.HOST_ABSENT)
    inv = _inventory(ports=[_port("10.0.0.6", ["sg-1"])],
                     rules=[_rule("sg-1", 22, 22)])
    assert exposure.build_findings([host], [], inv) == []


# --- Vista esterna -----------------------------------------------------------

def test_servizio_confermato_dal_floating_ip():
    host = _host("h1", "10.0.0.5")
    services = [_service("h1", 22, view=models.VIEW_INTERNAL),
                _service("h1", 22, view=models.VIEW_EXTERNAL)]
    inv = _inventory(
        ports=[_port("10.0.0.5", ["sg-1"])],
        rules=[_rule("sg-1", 22, 22, remote="10.0.0.0/24")],
        floating_ips=[_obj(fixed_ip_address="10.0.0.5",
                           floating_ip_address="172.24.4.10", port_id="p1")])

    findings = exposure.build_findings([host], services, inv)
    reachable = [f for f in findings
                 if f["finding_type"] == models.FINDING_EXTERNALLY_REACHABLE]
    assert len(reachable) == 1
    assert reachable[0]["severity"] == models.SEVERITY_INFO
    assert "172.24.4.10" in reachable[0]["message"]


def test_servizio_visto_solo_da_fuori():
    host = _host("h1", "10.0.0.5")
    # Solo vista esterna: internamente non era stato censito.
    services = [_service("h1", 8080, name="http", view=models.VIEW_EXTERNAL)]
    inv = _inventory(
        floating_ips=[_obj(fixed_ip_address="10.0.0.5",
                           floating_ip_address="172.24.4.10", port_id="p1")])

    findings = exposure.build_findings([host], services, inv)
    only = [f for f in findings
            if f["finding_type"] == models.FINDING_EXTERNAL_ONLY]
    assert len(only) == 1
    assert only[0]["port_number"] == 8080
    assert only[0]["severity"] == models.SEVERITY_MEDIUM


def test_floating_ip_sprecato_se_non_risponde_nulla():
    host = _host("h1", "10.0.0.5")
    services = [_service("h1", 22, view=models.VIEW_INTERNAL)]  # nessun esterno
    inv = _inventory(
        floating_ips=[_obj(fixed_ip_address="10.0.0.5",
                           floating_ip_address="172.24.4.10", port_id="p1")])

    findings = exposure.build_findings([host], services, inv)
    wasted = [f for f in findings
              if f["finding_type"] == models.FINDING_WASTED_FLOATING_IP]
    assert len(wasted) == 1
    assert wasted[0]["ip_address"] == "172.24.4.10"


def test_floating_ip_non_associato_e_sprecato():
    inv = _inventory(
        floating_ips=[_obj(fixed_ip_address=None,
                           floating_ip_address="172.24.4.11", port_id=None)])
    findings = exposure.build_findings([], [], inv)
    wasted = [f for f in findings
              if f["finding_type"] == models.FINDING_WASTED_FLOATING_IP]
    assert len(wasted) == 1
    assert "non è associato" in wasted[0]["message"]


# --- Giro completo sul database ----------------------------------------------

@pytest.fixture
def db(tmp_path):
    conf.load([])
    conf.CONF.set_override(
        "connection", f"sqlite:///{tmp_path / 'test.sqlite'}", group="database")
    api.reset()
    migration.upgrade()
    yield
    api.reset()


def test_compute_and_save_e_ordinamento_per_gravita(db):
    scan = api.create_scan("progetto-1", models.TRIGGER_MANUAL)
    # Un host censito con ssh aperto a tutti (alta) e una regola inutile (bassa).
    hosts = api.save_hosts(scan.id, [
        {"ip_address": "10.0.0.5", "classification": models.HOST_KNOWN,
         "network_id": "net-1", "neutron_port_id": "port-1"},
    ])
    api.save_services([
        {"host_id": hosts[0].id, "port_number": 22, "protocol": "tcp",
         "name": "ssh", "product": None, "version": None,
         "view": models.VIEW_INTERNAL},
    ])
    api.save_inventory(
        servers=[], ports=[models.InventoryPort(
            scan_id=scan.id, port_id="port-1", network_id="net-1",
            ip_address="10.0.0.5", security_group_ids=json.dumps(["sg-1"]))],
        floating_ips=[],
        security_groups=[models.InventorySecurityGroup(
            scan_id=scan.id, security_group_id="sg-1", name="demo")],
        rules=[
            models.InventorySecurityGroupRule(
                scan_id=scan.id, rule_id="r1", security_group_id="sg-1",
                direction="ingress", protocol="tcp", port_range_min=22,
                port_range_max=22, remote_ip_prefix="0.0.0.0/0"),
            models.InventorySecurityGroupRule(
                scan_id=scan.id, rule_id="r2", security_group_id="sg-1",
                direction="ingress", protocol="tcp", port_range_min=3306,
                port_range_max=3306, remote_ip_prefix="0.0.0.0/0"),
        ])

    saved = exposure.compute_and_save(scan.id)
    assert len(saved) == 2

    findings = api.get_findings(scan.id)
    # get_findings ordina per gravità: prima l'esposizione eccessiva (alta),
    # poi la regola inutile (bassa).
    assert [f.finding_type for f in findings] == [
        models.FINDING_OVEREXPOSED, models.FINDING_USELESS_RULE]
    assert findings[0].severity == models.SEVERITY_HIGH
