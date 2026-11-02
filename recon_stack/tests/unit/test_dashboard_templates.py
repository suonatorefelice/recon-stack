# Controlla che i template della dashboard stiano dove Horizon li cerca.
#
# Horizon non usa il caricatore standard di Django per i template dei pannelli:
# per un nome come "recon/hosts/index.html" (dashboard/pannello/resto) cerca il
# file in <cartella del pannello>/templates/<pannello>/<resto>, cioè
#   recon_stack/dashboard/recon/hosts/templates/hosts/index.html
# senza la cartella "recon/" in mezzo (horizon/loaders.py e
# Dashboard.register in horizon/base.py). Un file nel posto sbagliato si
# scopre solo aprendo la pagina, con un errore 500 "TemplateDoesNotExist":
# è successo davvero nel primo test su DevStack.
#
# Il test non importa Horizon (sul Mac non è installato): legge i nomi dei
# template dalle viste come testo e controlla che il file esista.

import pathlib
import re

DASHBOARD_DIR = pathlib.Path(__file__).parents[2] / "dashboard" / "recon"
TEMPLATE_NAME = re.compile(r'template_name\s*=\s*"([^"]+)"')


def _template_names():
    for views in sorted(DASHBOARD_DIR.glob("*/views.py")):
        for name in TEMPLATE_NAME.findall(views.read_text()):
            yield views.parent, name


def test_ci_sono_template_da_controllare():
    assert list(_template_names()), "nessuna vista con template_name trovata"


def test_ogni_template_sta_dove_lo_cerca_horizon():
    for panel_dir, name in _template_names():
        dashboard, panel, rest = name.split("/", 2)
        assert dashboard == "recon", name
        assert panel == panel_dir.name, f"{name} usato nel pannello {panel_dir.name}"
        expected = panel_dir / "templates" / panel / rest
        assert expected.is_file(), f"manca {expected.relative_to(DASHBOARD_DIR)}"
