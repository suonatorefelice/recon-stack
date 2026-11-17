# Controlla che gli indirizzi di dettaglio della dashboard non catturino i
# nomi dei pannelli.
#
# "hosts" è il pannello predefinito: Horizon monta i suoi indirizzi anche alla
# radice della dashboard, quindi /recon/hosts/ passa anche dal pattern del
# dettaglio host. Con un pattern troppo largo ([^/]+) quell'indirizzo sarebbe
# letto come "dettaglio dell'host con id hosts".
# Il dettaglio deve accettare solo UUID.
#
# Django non è installato sul Mac: leggiamo dal file, come testo, il valore di
# ID senza importare il modulo.

import ast
import pathlib
import re
import uuid

import pytest

DASHBOARD_DIR = pathlib.Path(__file__).parents[2] / "dashboard" / "recon"


def _id_pattern(panel):
    tree = ast.parse((DASHBOARD_DIR / panel / "urls.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and node.targets[0].id == "ID":
            return node.value.value
    raise AssertionError(f"ID non definito in {panel}/urls.py")


@pytest.mark.parametrize("panel", ["hosts", "scans"])
def test_il_dettaglio_accetta_un_uuid(panel):
    assert re.fullmatch(_id_pattern(panel), str(uuid.uuid4()))


@pytest.mark.parametrize("panel", ["hosts", "scans"])
@pytest.mark.parametrize("slug", ["hosts", "services", "scans", "start"])
def test_il_dettaglio_non_cattura_i_nomi_dei_pannelli(panel, slug):
    assert re.fullmatch(_id_pattern(panel), slug) is None


# --- Host/Servizi per progetto e azione Report (Horizon non importabile: testo) ---

def _src(*parts):
    return (DASHBOARD_DIR.joinpath(*parts)).read_text()


@pytest.mark.parametrize("panel,call", [("hosts", "list_hosts"),
                                        ("services", "list_services")])
def test_le_viste_passano_lo_scan_id(panel, call):
    # Host e Servizi lavorano sulla scansione dell'URL (?scan_id=); senza
    # parametro vale il default della API, lo stesso del Riepilogo.
    src = _src(panel, "views.py")
    assert re.search(rf"{call}\([^)]*scan_id=scan_id", src, re.S)
    assert 'self.request.GET.get("scan_id")' in src


def test_esiste_l_url_report_con_uuid():
    src = _src("scans", "urls.py")
    assert 'name="report"' in src and "report/$" in src
    assert "views.ReportView" in src


def test_la_tabella_scansioni_ha_l_azione_report():
    src = _src("scans", "tables.py")
    assert "class ApriReport" in src and "horizon:recon:scans:report" in src
    assert re.search(r"row_actions = \([^)]*ApriReport", src)


def test_report_view_costruisce_dalla_api():
    # Il report è una pagina Horizon costruita dalle rotte /v1 (scansione,
    # segnalazioni, host e servizi).
    src = _src("scans", "views.py")
    assert "class ReportView" in src
    assert "list_hosts(scan_id=scan_id)" in src
    assert "get_scan_exposure(scan_id)" in src
