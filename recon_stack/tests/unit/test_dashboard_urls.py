# Controlla che gli indirizzi di dettaglio della dashboard non catturino i
# nomi dei pannelli.
#
# "hosts" è il pannello predefinito: Horizon monta i suoi indirizzi anche alla
# radice della dashboard, quindi /recon/hosts/ passa anche dal pattern del
# dettaglio host. Con un pattern troppo largo ([^/]+) quell'indirizzo veniva
# letto come "dettaglio dell'host con id hosts" (trovato nel test su DevStack).
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
