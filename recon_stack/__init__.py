# Pacchetto del servizio Recon-Stack.
#
# Sottopacchetti:
#   api/  applicazione web (processo recon-api)
#   cmd/  programmi avviabili da riga di comando (processo recon-scanner)
# Gli altri (scanner/, db/, privsep/, report/) arrivano con gli step successivi,
# vedi docs/piano.md.

import warnings

# oslo.privsep (ADR 0007) importa eventlet, che a ogni avvio stampa un lungo
# avviso di deprecazione in testa all'output. Non dipende da una nostra scelta
# (non usiamo eventlet direttamente) e rende illeggibile il riepilogo dei
# comandi: lo nascondiamo. Questo modulo viene caricato per primo, prima che
# privsep importi oslo_privsep, quindi il filtro fa in tempo ad attivarsi.
warnings.filterwarnings("ignore", message=r"(?s).*Eventlet is deprecated")
