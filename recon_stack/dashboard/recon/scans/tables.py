# La tabella delle scansioni (storico) e l'azione "Avvia scansione".

from django.utils.translation import gettext_lazy as _
from horizon import tables


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
    id = tables.Column("id", verbose_name=_("ID"),
                       link="horizon:recon:scans:detail")
    project_id = tables.Column("project_id", verbose_name=_("Progetto"))
    status = tables.Column("status", verbose_name=_("Stato"))
    trigger = tables.Column("trigger", verbose_name=_("Origine"))
    created_at = tables.Column("created_at", verbose_name=_("Creata"))

    class Meta(object):
        name = "scans"
        verbose_name = _("Scansioni")
        table_actions = (StartScan,)
