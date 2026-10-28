# Pacchetto del servizio Recon-Stack.
#
# Sottopacchetti:
#   api/        il servizio recon-api: applicazione Flask servita da uwsgi, con
#               lo scheduler delle scansioni periodiche
#   cmd/        recon-stack-dbsync, che crea lo schema del database
#   scanner/    scansioni: inventario, discovery, esecuzione e scheduler
#   privsep/    le sole funzioni eseguite con privilegi (oslo.privsep, ADR 0007)
#   db/         modelli e accesso al database
#   dashboard/  pannello Horizon

import warnings

# oslo.privsep (ADR 0007) importa eventlet, che a ogni avvio stampa un lungo
# avviso di deprecazione in testa all'output. Non dipende da una nostra scelta
# (non usiamo eventlet direttamente) e rende illeggibile il riepilogo dei
# comandi: lo nascondiamo. Questo modulo viene caricato per primo, prima che
# privsep importi oslo_privsep, quindi il filtro fa in tempo ad attivarsi.
warnings.filterwarnings("ignore", message=r"(?s).*Eventlet is deprecated")
