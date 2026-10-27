# Test del report (recon_stack/report/*) e del comando recon-stack-report.
#
# La raccolta dei dati e la redaction si provano sul database; la mappa (DOT) e
# l'HTML si provano sul dizionario dei dati, senza bisogno di Graphviz né di un
# browser. Il test del comando usa un database vero in una cartella temporanea.

import pytest

from recon_stack import conf
from recon_stack.db import api as db
from recon_stack.db import migration
from recon_stack.db import models
from recon_stack.report import builder
from recon_stack.report import render
from recon_stack.report import topology


@pytest.fixture
def database(tmp_path):
    conf.load([])
    conf.CONF.set_override(
        "connection", f"sqlite:///{tmp_path / 'test.sqlite'}", group="database")
    db.reset()
    migration.upgrade()
    yield
    db.reset()


def _seed(scan_status=models.SCAN_DONE):
    """Crea una scansione completata con un host, un servizio e una segnalazione."""
    scan = db.create_scan("progetto-vero-123", models.TRIGGER_MANUAL,
                          status=scan_status)
    hosts = db.save_hosts(scan.id, [
        {"ip_address": "10.10.10.5", "network_id": "net-abc", "subnet_id": "sub-1",
         "neutron_port_id": "port-1", "server_id": "vm-1", "server_name": "web-reale",
         "classification": models.HOST_KNOWN},
        {"ip_address": "10.10.10.50", "network_id": "net-abc", "subnet_id": None,
         "neutron_port_id": None, "server_id": None, "server_name": None,
         "classification": models.HOST_UNKNOWN},
    ])
    web = next(h for h in hosts if h.ip_address == "10.10.10.5")
    db.save_services([
        {"host_id": web.id, "port_number": 22, "protocol": "tcp", "name": "ssh",
         "product": "OpenSSH", "version": "8.9p1", "view": models.VIEW_INTERNAL},
        {"host_id": web.id, "port_number": 22, "protocol": "tcp", "name": "ssh",
         "product": None, "version": None, "view": models.VIEW_EXTERNAL},
    ])
    db.save_inventory(
        servers=[], ports=[], floating_ips=[models.InventoryFloatingIp(
            scan_id=scan.id, floating_ip_id="f1",
            floating_ip_address="172.24.4.10", fixed_ip_address="10.10.10.5",
            port_id="port-1")])
    db.save_findings([
        {"scan_id": scan.id, "finding_type": models.FINDING_OVEREXPOSED,
         "severity": models.SEVERITY_HIGH, "ip_address": "10.10.10.5",
         "port_number": 22, "protocol": "tcp",
         "message": "Il servizio ssh (22/tcp) su 10.10.10.5 è raggiungibile da "
                    "qualunque indirizzo (0.0.0.0/0)."},
    ])
    return scan


# --- Raccolta dati -----------------------------------------------------------

def test_gather_raccoglie_tutto(database):
    scan = _seed()
    data = builder.gather(scan.id)

    assert data["scan"]["project_id"] == "progetto-vero-123"
    assert data["summary"]["hosts_total"] == 2
    assert data["summary"]["hosts_by_classification"]["unknown"] == 1
    web = next(h for h in data["hosts"] if h["ip_address"] == "10.10.10.5")
    assert [s["port_number"] for s in web["services_internal"]] == [22]
    assert [s["port_number"] for s in web["services_external"]] == [22]
    assert data["findings"][0]["type"] == models.FINDING_OVEREXPOSED
    assert data["floating_ips"][0]["floating_ip_address"] == "172.24.4.10"


def test_gather_scansione_inesistente(database):
    assert builder.gather("non-esiste") is None


# --- Redaction ---------------------------------------------------------------

def test_redact_sostituisce_indirizzi_nomi_e_id(database):
    data = builder.gather(_seed().id)
    red = builder.redact(data)

    assert red["redacted"] is True
    # Niente dati veri né nei campi né nei testi delle segnalazioni.
    testo = str(red)
    assert "10.10.10.5" not in testo
    assert "172.24.4.10" not in testo
    assert "web-reale" not in testo
    assert "progetto-vero-123" not in testo
    # Lo stesso host ha lo stesso pseudonimo nel campo e nel messaggio.
    web = next(h for h in red["hosts"] if h["classification"] == "known")
    assert web["ip_address"] in red["findings"][0]["message"]
    # I nomi dei servizi non sono sensibili: restano.
    assert "ssh" in str(red["hosts"])


def test_redact_e_coerente_stesso_valore_stesso_pseudonimo(database):
    data = builder.gather(_seed().id)
    red = builder.redact(data)
    # Il floating IP inoltra verso 10.10.10.5: nei dati il fixed_ip del floating
    # e l'ip dell'host devono ricevere lo stesso pseudonimo.
    web = next(h for h in red["hosts"] if h["classification"] == "known")
    assert red["floating_ips"][0]["fixed_ip_address"] == web["ip_address"]


# --- Mappa DOT ---------------------------------------------------------------

def test_build_dot_contiene_reti_e_host(database):
    data = builder.gather(_seed().id)
    dot = topology.build_dot(data)
    assert dot.startswith("digraph recon {")
    assert "rete" in dot
    assert "10.10.10.5" in dot
    assert "22/tcp ssh" in dot


# --- HTML --------------------------------------------------------------------

def test_render_html_include_segnalazioni_e_host(database):
    data = builder.gather(_seed().id)
    html = render.render_html(data, svg="<svg></svg>")
    assert "<title>Report Recon-Stack" in html
    assert "overexposed" in html
    assert "10.10.10.5" in html
    assert "<svg></svg>" in html


def test_render_html_redatto_segnala_la_versione_condivisibile(database):
    data = builder.redact(builder.gather(_seed().id))
    html = render.render_html(data)
    assert "condivisibile" in html
    assert "10.10.10.5" not in html


# --- Comando -----------------------------------------------------------------

def test_comando_report_scrive_i_file(database, tmp_path, monkeypatch, capsys):
    from recon_stack.cmd import report as cmd_report
    scan = _seed()
    # Non dipendiamo da Graphviz nel test: fingiamo che `dot` manchi.
    monkeypatch.setattr(topology, "dot_available", lambda: False)

    out_dir = tmp_path / "rep"
    assert cmd_report.main(["--scan", scan.id, "--output", str(out_dir)]) == 0
    assert (out_dir / "report.html").exists()
    assert (out_dir / "report.dot").exists()
    assert "report.html" in capsys.readouterr().out


def test_comando_report_senza_scansioni(database, capsys):
    from recon_stack.cmd import report as cmd_report
    assert cmd_report.main([]) == 1
