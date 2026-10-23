# Test della configurazione (recon_stack/conf.py).

import pathlib

from recon_stack import conf

SAMPLE = pathlib.Path(__file__).parents[3] / "etc" / "recon-stack.conf.sample"


def test_valori_predefiniti():
    conf.load([])
    assert conf.CONF.debug is False
    assert conf.CONF.api.port == 5238
    assert conf.CONF.scanner.heartbeat_interval == 60


def test_il_file_di_configurazione_cambia_i_valori(tmp_path):
    # tmp_path è una cartella temporanea che pytest crea e poi cancella.
    conf_file = tmp_path / "recon-stack.conf"
    conf_file.write_text("[DEFAULT]\ndebug = true\n[scanner]\nheartbeat_interval = 10\n")
    conf.load(["--config-file", str(conf_file)])
    assert conf.CONF.debug is True
    assert conf.CONF.scanner.heartbeat_interval == 10


def test_il_file_di_esempio_elenca_tutte_le_opzioni():
    # Il file etc/recon-stack.conf.sample è scritto a mano: questo test
    # ricorda di aggiornarlo quando si aggiunge un'opzione in conf.py.
    text = SAMPLE.read_text()
    for group, opts in conf.list_opts():
        section = "DEFAULT" if group is None else group.name
        assert f"[{section}]" in text
        for opt in opts:
            assert f"#{opt.name} =" in text, f"manca {section}.{opt.name}"
