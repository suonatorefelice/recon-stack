# Test del motore di esposizione (scanner/exposure.py).
#
# build_findings non tocca il database: costruiamo host, servizi e inventario a
# mano (SimpleNamespace, come gli oggetti del database) e controlliamo quali
# segnalazioni produce. Un test finale prova il giro completo sul database
# (compute_and_save + get_findings), compreso l'ordinamento per gravità.

import collections
import types

import pytest

from recon_stack.db import api
from recon_stack.db import models
from recon_stack.scanner import exposure
from recon_stack.scanner import inventory


def _obj(**kwargs):
    return types.SimpleNamespace(**kwargs)


def _host(host_id, ip, classification=models.HOST_KNOWN, network_id="net-1"):
    return _obj(id=host_id, ip_address=ip, classification=classification,
                network_id=network_id)


def _service(host_id, port, name="ssh", protocol="tcp", view=models.VIEW_INTERNAL):
    return _obj(host_id=host_id, port_number=port, protocol=protocol,
                name=name, view=view)


def _port(ip, sg_ids, device_owner="compute:nova", port_security=True,
          network_id="net-1", port_id=None):
    return _obj(ip_address=ip, security_group_ids=tuple(sg_ids),
                device_owner=device_owner, port_security_enabled=port_security,
                network_id=network_id, port_id=port_id)


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


# --- Stesso IP su reti diverse -----------------------------------------------

def test_ip_sovrapposti_su_due_reti_usano_il_security_group_giusto():
    # Due reti riusano 10.0.0.5: la porta della rete A apre la 22 a tutti, quella
    # della rete B non apre nulla. Ogni host deve essere giudicato dai SUOI SG.
    host_a = _host("ha", "10.0.0.5", network_id="net-a")
    host_b = _host("hb", "10.0.0.5", network_id="net-b")
    services = [_service("ha", 22), _service("hb", 22)]
    inv = _inventory(
        ports=[_port("10.0.0.5", ["sg-a"], network_id="net-a"),
               _port("10.0.0.5", ["sg-b"], network_id="net-b")],
        rules=[_rule("sg-a", 22, 22, remote="0.0.0.0/0")])

    findings = exposure.build_findings([host_a, host_b], services, inv)
    over = [f for f in findings if f["finding_type"] == models.FINDING_OVEREXPOSED]
    latent = [f for f in findings
              if f["finding_type"] == models.FINDING_LATENT_SERVICE]
    assert len(over) == 1 and len(latent) == 1


def test_port_security_e_floating_ip_seguono_la_rete():
    host_a = _host("ha", "10.0.0.5", network_id="net-a")
    host_b = _host("hb", "10.0.0.5", network_id="net-b")
    inv = _inventory(
        ports=[_port("10.0.0.5", [], network_id="net-a", port_security=False),
               _port("10.0.0.5", [], network_id="net-b", port_id="pb")],
        floating_ips=[_obj(fixed_ip_address="10.0.0.5",
                           floating_ip_address="172.24.4.10", port_id="pb")])
    services = [_service("hb", 22, view=models.VIEW_EXTERNAL)]

    findings = exposure.build_findings([host_a, host_b], services, inv)
    nops = [f for f in findings
            if f["finding_type"] == models.FINDING_NO_PORT_SECURITY]
    assert len(nops) == 1
    # Il floating IP è dell'host B (rete B), che risponde da fuori: non sprecato.
    assert not [f for f in findings
                if f["finding_type"] == models.FINDING_WASTED_FLOATING_IP]


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
def db(clean_database):
    # clean_database (in conftest.py) prepara un database MySQL di test pulito.
    yield


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
    # L'inventario non è nel database: arriva dalla memoria.
    inv = _inventory(
        ports=[_port("10.0.0.5", ["sg-1"], port_id="port-1")],
        rules=[_rule("sg-1", 22, 22), _rule("sg-1", 3306, 3306)])

    saved = exposure.compute_and_save(scan.id, inv)
    assert len(saved) == 2

    findings = api.get_findings(scan.id)
    # get_findings ordina per gravità: prima l'esposizione eccessiva (alta),
    # poi la regola inutile (bassa).
    assert [f.finding_type for f in findings] == [
        models.FINDING_OVEREXPOSED, models.FINDING_USELESS_RULE]
    assert findings[0].severity == models.SEVERITY_HIGH


def test_build_findings_da_namedtuple():
    # Le 7 segnalazioni attese della demo, con l'inventario fatto di
    # namedtuple (quelli di inventory.collect) e non di oggetti del database.
    Port, Fip, Rule = inventory.PortInfo, inventory.FloatingIpInfo, inventory.RuleInfo
    ports = [
        Port("p-a", "net-1", "sub-1", "10.0.0.5", "compute:nova", "vm-a",
             ("sg-a",), False),
        Port("p-b", "net-1", "sub-1", "10.0.0.6", "compute:nova", "vm-b",
             ("sg-b",), True),
    ]
    fips = [Fip("172.24.4.10", "10.0.0.6", "p-b")]
    rules = [
        Rule("sg-b", "ingress", "tcp", 22, 22, "0.0.0.0/0", None),
        Rule("sg-b", "ingress", "tcp", 3306, 3306, "0.0.0.0/0", None),
        Rule("sg-b", "ingress", "tcp", 5432, 5432, "0.0.0.0/0", None),
    ]
    hosts = [
        _host("ha", "10.0.0.5"), _host("hb", "10.0.0.6"),
        _host("hc", "10.0.0.50", models.HOST_UNKNOWN),
    ]
    services = [
        _service("hb", 22), _service("hb", 80, name="http"),
        _service("hb", 22, view=models.VIEW_EXTERNAL),
        _service("hc", 22),
    ]
    inv = {"ports": ports, "floating_ips": fips, "security_group_rules": rules}

    findings = exposure.build_findings(hosts, services, inv)

    assert collections.Counter(
        (f["severity"], f["finding_type"]) for f in findings) == {
        (models.SEVERITY_HIGH, models.FINDING_NO_PORT_SECURITY): 1,
        (models.SEVERITY_HIGH, models.FINDING_OVEREXPOSED): 1,
        (models.SEVERITY_HIGH, models.FINDING_UNKNOWN_EXPOSED): 1,
        (models.SEVERITY_MEDIUM, models.FINDING_LATENT_SERVICE): 1,
        (models.SEVERITY_LOW, models.FINDING_USELESS_RULE): 2,
        (models.SEVERITY_INFO, models.FINDING_EXTERNALLY_REACHABLE): 1,
    }


# --- Port security disattivata ----------------------------------------------

def test_port_security_disattivata_e_esposta_non_latente():
    # Una porta senza port security non ha security group: i suoi servizi
    # sono esposti a tutti, non "latenti" (nessuna regola li prevede).
    host = _host("h1", "10.0.0.5")
    services = [_service("h1", 22)]
    inv = _inventory(ports=[_port("10.0.0.5", [], port_security=False)])

    findings = exposure.build_findings([host], services, inv)
    assert _types(findings) == {models.FINDING_NO_PORT_SECURITY}
    assert findings[0]["severity"] == models.SEVERITY_HIGH
    assert "22/tcp" in findings[0]["message"]


def test_port_security_ignota_vale_il_confronto_con_le_regole():
    # Quando il dato port_security manca (None), decidono le regole del
    # security group, come per una porta protetta.
    host = _host("h1", "10.0.0.5")
    inv = _inventory(ports=[_port("10.0.0.5", ["sg-1"], port_security=None)],
                     rules=[_rule("sg-1", 22, 22)])
    findings = exposure.build_findings([host], [_service("h1", 22)], inv)
    assert models.FINDING_OVEREXPOSED in _types(findings)
    assert models.FINDING_NO_PORT_SECURITY not in _types(findings)


# --- Regola dello scanner (ADR 0012) ----------------------------------------

def _inventory_con_scanner(rules):
    return _inventory(
        ports=[_port("10.0.0.5", ["sg-1"]),
               # La porta dei metadati di OVN: la sorgente dello scanner.
               _port("10.0.0.2", [], device_owner="network:distributed",
                     port_security=False)],
        rules=rules)


def test_servizio_coperto_solo_dalla_regola_dello_scanner_e_latente():
    host = _host("h1", "10.0.0.5")
    inv = _inventory_con_scanner([
        _rule("sg-1", 22, 22),                                   # ssh dichiarato
        _rule("sg-1", None, None, remote="10.0.0.2/32"),         # regola scanner
    ])
    services = [_service("h1", 22), _service("h1", 9090, name=None)]

    findings = exposure.build_findings([host], services, inv)
    latenti = [f for f in findings
               if f["finding_type"] == models.FINDING_LATENT_SERVICE]
    # La 9090 la permette solo la regola dello scanner: è latente.
    assert [f["port_number"] for f in latenti] == [9090]


def test_la_regola_dello_scanner_non_e_una_regola_inutile():
    host = _host("h1", "10.0.0.5")
    inv = _inventory_con_scanner([
        _rule("sg-1", 1, 65535, remote="10.0.0.2/32"),  # tutte le porte, solo scanner
    ])
    findings = exposure.build_findings([host], [_service("h1", 22)], inv)
    assert models.FINDING_USELESS_RULE not in _types(findings)


def test_una_regola_ristretta_a_un_altro_indirizzo_non_e_dello_scanner():
    # Un /32 verso un indirizzo qualunque è una regola normale: copre il servizio.
    host = _host("h1", "10.0.0.5")
    inv = _inventory_con_scanner([_rule("sg-1", 9090, 9090, remote="10.0.0.99/32")])
    findings = exposure.build_findings(
        [host], [_service("h1", 9090, name=None)], inv)
    assert models.FINDING_LATENT_SERVICE not in _types(findings)


def test_regola_ristretta_senza_regola_scanner_non_e_inutile():
    # La 3306 è aperta solo a 10.0.0.5/32: lo scanner la vede "filtered", quindi
    # l'assenza del servizio non dimostra che la regola sia inutile.
    host = _host("h1", "10.0.0.5")
    inv = _inventory_con_scanner([_rule("sg-1", 3306, 3306, remote="10.0.0.5/32")])
    findings = exposure.build_findings([host], [_service("h1", 22)], inv)
    assert models.FINDING_USELESS_RULE not in _types(findings)


def test_regola_ristretta_con_regola_scanner_resta_inutile():
    # Una regola dello scanner copre la 3306: lo scanner poteva vederla e lì
    # non c'è nessun servizio, quindi la regola ristretta è davvero inutile.
    host = _host("h1", "10.0.0.5")
    inv = _inventory_con_scanner([
        _rule("sg-1", 3306, 3306, remote="10.0.0.5/32"),
        _rule("sg-1", 3306, 3306, remote="10.0.0.2/32"),  # regola scanner
    ])
    findings = exposure.build_findings([host], [_service("h1", 22)], inv)
    useless = [f for f in findings
               if f["finding_type"] == models.FINDING_USELESS_RULE]
    assert [f["port_number"] for f in useless] == [3306]


def test_porte_di_infrastruttura_senza_port_security_non_sono_segnalate():
    # Router e metadati in Neutron non hanno mai la port security: segnalarli
    # sarebbe un falso positivo.
    hosts = [_host("r", "10.0.0.1"), _host("m", "10.0.0.2")]
    inv = _inventory(ports=[
        _port("10.0.0.1", [], device_owner="network:router_interface",
              port_security=False),
        _port("10.0.0.2", [], device_owner="network:distributed",
              port_security=False),
    ])
    assert exposure.build_findings(hosts, [], inv) == []
