# Il plugin tempest di Recon-Stack (step 13).
#
# tempest è lo strumento con cui OpenStack prova i servizi su un cloud vero,
# dall'esterno, via API. Un "plugin tempest" è il modo in cui un progetto come il
# nostro aggiunge i propri test a tempest: questa classe dice a tempest dove
# trovare i test (load_tests) e quali opzioni di configurazione aggiungere
# (register_opts / get_opt_lists).
#
# Il plugin si registra con l'entry point "tempest.test_plugins" in setup.cfg.
# tempest lo scopre da solo quando il pacchetto è installato nell'ambiente di
# tempest sul nodo DevStack.

import os

from tempest import config
from tempest.test_discovery import plugins

from recon_stack.tests.tempest import config as recon_config


class ReconTempestPlugin(plugins.TempestPlugin):
    """Registra i test e le opzioni di Recon-Stack dentro tempest."""

    def load_tests(self):
        # Diciamo a tempest in quale cartella cercare i nostri test e qual è la
        # radice del pacchetto, come fanno tutti i plugin tempest.
        base_path = os.path.split(os.path.dirname(os.path.abspath(__file__)))[0]
        base_path = os.path.split(base_path)[0]
        test_dir = "recon_stack/tests/tempest/tests"
        full_test_dir = os.path.join(base_path, test_dir)
        return full_test_dir, base_path

    def register_opts(self, conf):
        # Aggiunge la sezione [recon] alla configurazione di tempest.
        config.register_opt_group(conf, recon_config.recon_group,
                                  recon_config.ReconGroup)

    def get_opt_lists(self):
        # Serve a "tempest config" per elencare le nostre opzioni.
        return [(recon_config.recon_group.name, recon_config.ReconGroup)]
