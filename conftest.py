# Configurazione di pytest per l'intero repository.
#
# I test unitari (recon_stack/tests/unit) girano senza OpenStack, sul Mac. I test
# tempest (recon_stack/tests/tempest) invece hanno bisogno di tempest e di un
# DevStack vero: qui diciamo a pytest di NON raccoglierli, così un "pytest" dato
# nella cartella del progetto sul Mac non prova a importarli e non fallisce per
# via di tempest mancante. Su DevStack i test tempest si eseguono con tempest,
# non con pytest (vedi recon_stack/tests/tempest/README.md).

collect_ignore_glob = ["recon_stack/tests/tempest/*"]
