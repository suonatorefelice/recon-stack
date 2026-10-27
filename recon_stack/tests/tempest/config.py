# Opzioni di configurazione del plugin tempest di Recon-Stack.
#
# tempest legge la sua configurazione da un file (tempest.conf). Qui dichiariamo
# una sezione [recon] con le poche opzioni che servono ai test: se il servizio
# va provato e il nome del progetto demo da usare come bersaglio. I valori
# predefiniti vanno bene per un DevStack con il plugin installato e il progetto
# creato da demo/setup_demo.sh.

from oslo_config import cfg

recon_group = cfg.OptGroup(name="recon",
                           title="Opzioni dei test di Recon-Stack")

ReconGroup = [
    cfg.BoolOpt("enabled",
                default=True,
                help="Esegue i test di Recon-Stack."),
    cfg.StrOpt("demo_project",
               default="recon-demo",
               help="Nome del progetto demo da scansionare (demo/setup_demo.sh)."),
    cfg.IntOpt("scan_timeout",
               default=300,
               help="Secondi massimi di attesa perché una scansione finisca."),
]
