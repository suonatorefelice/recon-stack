# Test della configurazione (recon_stack/conf.py).

import pathlib

from recon_stack import conf

SAMPLE = pathlib.Path(__file__).parents[3] / "etc" / "recon-stack.conf.sample"


def test_valori_predefiniti():
    # default_config_files=[] evita di leggere i file di sistema (es.
    # /etc/recon-stack/recon-stack.conf, presente su DevStack): qui vogliamo
    # verificare i valori predefiniti del codice, non quelli di un file già
    # installato sulla macchina.
    conf.CONF([], project="recon-stack", default_config_files=[])
    assert conf.CONF.debug is False
    assert conf.CONF.scanner.min_scan_interval == 60


def test_il_file_di_configurazione_cambia_i_valori(tmp_path):
    # tmp_path è una cartella temporanea che pytest crea e poi cancella.
    conf_file = tmp_path / "recon-stack.conf"
    conf_file.write_text("[DEFAULT]\ndebug = true\n[scanner]\nmin_scan_interval = 10\n")
    conf.load(["--config-file", str(conf_file)])
    assert conf.CONF.debug is True
    assert conf.CONF.scanner.min_scan_interval == 10


def test_il_file_di_esempio_elenca_tutte_le_opzioni():
    # Il file etc/recon-stack.conf.sample è generato da oslo-config-generator
    # (--namespace recon_stack): questo test ricorda di rigenerarlo quando si
    # aggiunge un'opzione in conf.py.
    text = SAMPLE.read_text()
    for group, opts in conf.list_opts():
        section = "DEFAULT" if group is None else group.name
        assert f"[{section}]" in text
        for opt in opts:
            assert f"#{opt.name} =" in text, f"manca {section}.{opt.name}"
