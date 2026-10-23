# Richiesta di una scansione: regole d'avvio e log (Step 5).
#
# Quando un admin chiede una scansione (lo farà POST /v1/scans, step 8), prima
# di avviarla controlliamo due cose:
#   1. il ruolo: solo admin può scansionare (ADR 0002);
#   2. la frequenza: non più di una scansione avviata ogni
#      [scanner] min_scan_interval secondi per lo stesso progetto.
#
# Un vincolo del progetto impone di registrare OGNI tentativo (chi, quando, su
# quale progetto): per questo ogni richiesta, anche quella rifiutata, crea una
# riga nella tabella scans. Una richiesta accettata nasce con stato PENDING e
# sarà lo scanner a eseguirla; una rifiutata nasce già con stato REJECTED e il
# motivo nel campo fault.
#
# Il controllo del perimetro NON è qui: avviene quando la scansione viene
# eseguita (scanner/perimeter.py, ADR 0005), perché il perimetro si ricalcola a
# quel momento leggendo Neutron.

import logging

from recon_stack import conf
from recon_stack.api import context as context_mod
from recon_stack.db import api as db
from recon_stack.db import models

LOG = logging.getLogger(__name__)


class RateLimited(Exception):
    """Richiesta rifiutata perché arrivata troppo presto dopo la precedente."""


def _seconds_since_last_scan(project_id):
    """Secondi trascorsi dall'ultima scansione AVVIATA del progetto.

    Contano solo le scansioni avviate davvero (non quelle già rifiutate, che
    non hanno mai toccato la rete): due richieste rifiutate di fila non devono
    farsi da limite a vicenda. None se non ce n'è nessuna.
    """
    for scan in db.list_scans(project_id=project_id):  # già ordinate, più recenti prima
        if scan.status != models.SCAN_REJECTED:
            return (models.utcnow() - scan.created_at).total_seconds()
    return None


def request_scan(context, project_id):
    """Valuta e registra una richiesta di scansione manuale.

    Restituisce la scansione creata (stato PENDING) se accettata. Se rifiutata,
    registra comunque il tentativo (stato REJECTED con il motivo) e solleva
    l'eccezione corrispondente, che l'endpoint tradurrà nella risposta HTTP:
      - NotAuthenticated  -> 401
      - NotAuthorized     -> 403
      - RateLimited       -> 429
    """
    def reject(fault, error):
        db.create_scan(
            project_id, models.TRIGGER_MANUAL,
            requested_by_user=context.user_id,
            requested_by_project=context.project_id,
            status=models.SCAN_REJECTED, fault=fault)
        LOG.warning("scansione rifiutata (progetto %s, utente %s): %s",
                    project_id, context.user_id, fault)
        raise error

    # 1. Ruolo admin.
    try:
        context.require_admin()
    except (context_mod.NotAuthenticated, context_mod.NotAuthorized) as exc:
        reject(str(exc), exc)

    # 2. Frequenza.
    min_interval = conf.CONF.scanner.min_scan_interval
    if min_interval > 0:
        elapsed = _seconds_since_last_scan(project_id)
        if elapsed is not None and elapsed < min_interval:
            wait = int(min_interval - elapsed)
            reject(
                f"scansione troppo frequente: attendere ancora {wait} s",
                RateLimited(f"riprovare fra {wait} s"))

    # Accettata: nasce PENDING, la eseguirà lo scanner.
    scan = db.create_scan(
        project_id, models.TRIGGER_MANUAL,
        requested_by_user=context.user_id,
        requested_by_project=context.project_id,
        status=models.SCAN_PENDING)
    LOG.info("scansione accettata (progetto %s, utente %s): %s",
             project_id, context.user_id, scan.id)
    return scan
