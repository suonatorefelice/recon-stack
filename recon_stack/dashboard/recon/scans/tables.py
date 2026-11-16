# La tabella delle scansioni (storico) e l'azione "Avvia scansione".

from django.utils.translation import gettext_lazy as _
from horizon import tables

from recon_stack.dashboard.recon import labels


# Funzioni di cella: estraggono il campo grezzo dalla riga e lo traducono con il
# modulo labels. La colonna "id" mostra l'UUID accorciato, ma il collegamento al
# dettaglio continua a usare l'id pieno della riga (Horizon risolve il link
# dall'id dell'oggetto, non dal testo mostrato).
def _status(scan):
    return labels.status_label(scan.status)


def _trigger(scan):
    return labels.trigger_label(scan.trigger)


def _created(scan):
    return labels.human_datetime(scan.created_at)


def _id(scan):
    return labels.short_uuid(scan.id)


def _project(scan):
    return labels.short_uuid(scan.project_id)


class StartScan(tables.LinkAction):
    """Pulsante che apre il modulo per avviare una nuova scansione."""

    name = "start"
    verbose_name = _("Avvia scansione")
    url = "horizon:recon:scans:start"
    classes = ("ajax-modal",)   # apre il form in una finestra modale
    icon = "plus"
    # Solo admin può avviare scansioni (ADR 0002); la API lo impone comunque.
    policy_rules = ()


class ScansTable(tables.DataTable):
    id = tables.Column(_id, verbose_name=_("ID"),
                       link="horizon:recon:scans:detail")
    project_id = tables.Column(_project, verbose_name=_("Progetto"))
    status = tables.Column(_status, verbose_name=_("Stato"))
    trigger = tables.Column(_trigger, verbose_name=_("Origine"))
    created_at = tables.Column(_created, verbose_name=_("Creata"))

    class Meta(object):
        name = "scans"
        verbose_name = _("Scansioni")
        table_actions = (StartScan,)
