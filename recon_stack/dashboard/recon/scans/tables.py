# La tabella delle scansioni (storico) e l'azione "Avvia scansione".

from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from horizon import tables

from recon_stack.dashboard import api
from recon_stack import vocab
from recon_stack.dashboard.recon import labels


# Funzioni di cella: estraggono il campo grezzo e lo traducono con labels. La
# colonna "id" mostra l'UUID accorciato, ma il link usa l'id pieno della riga.
def _trigger(scan):
    return labels.trigger_label(scan.trigger)


def _created(scan):
    return labels.human_datetime(scan.created_at)


def _id(scan):
    return labels.short_uuid(scan.id)


def _project(scan):
    return labels.short_uuid(scan.project_id)


def _phase(scan):
    # La fase ha senso solo mentre la scansione è in corso; phase_text torna ""
    # per le scansioni finite o vecchie (phase assente).
    return labels.phase_text(getattr(scan, "phase", None))


# Stato grezzo -> etichetta italiana (per la colonna Stato).
STATUS_DISPLAY = tuple(labels.STATUS_LABELS.items())
# Stato grezzo -> è uno stato finale? (Horizon confronta in minuscolo). Gli stati
# NON elencati (PENDING, RUNNING) sono "in transito": Horizon ri-sonda da sola la
# riga finché non diventano finali, aggiornando stato e fase senza ricaricare:
# lo fa la tabella con status=True e la UpdateRow (Meta.row_class), che a ogni
# giro rilegge la scansione da GET /v1/scans/<id>.
STATUS_CHOICES = (
    ("done", True),
    ("failed", False),
)


class StartScan(tables.LinkAction):
    """Pulsante che apre il modulo per avviare una nuova scansione."""

    name = "start"
    verbose_name = _("Avvia scansione")
    url = "horizon:recon:scans:start"
    classes = ("ajax-modal",)   # apre il form in una finestra modale
    icon = "plus"
    # Niente policy_rules: l'intera dashboard è riservata agli admin
    # (permissions in dashboard.py) e la API ricontrolla il ruolo.


class ApriDettaglio(tables.LinkAction):
    """Pulsante esplicito in riga che apre il dettaglio di una scansione (l'ID
    accorciato è già un link, ma poco evidente)."""

    name = "detail"
    verbose_name = _("Dettaglio")
    url = "horizon:recon:scans:detail"

    def get_link_url(self, datum):
        # L'URL usa l'id pieno della riga, non quello accorciato in tabella.
        return reverse(self.url, args=[datum.id])


class ApriReport(tables.LinkAction):
    """Pulsante in riga che apre il report HTML della scansione."""

    name = "report"
    verbose_name = _("Report")
    url = "horizon:recon:scans:report"

    def get_link_url(self, datum):
        return reverse(self.url, args=[datum.id])

    def allowed(self, request, datum=None):
        # Il report esiste solo per le scansioni finite con successo.
        return getattr(datum, "status", None) == vocab.SCAN_DONE


class UpdateRow(tables.Row):
    """Rilegge una scansione dalla API: con ajax=True Horizon ri-sonda da sola le
    righe non finali, così stato e fase avanzano senza ricaricare la pagina."""

    ajax = True

    def get_data(self, request, scan_id):
        return api.wrap(api.reconclient(request).get_scan(scan_id))


class ScansTable(tables.DataTable):
    id = tables.Column(_id, verbose_name=_("ID"),
                       link="horizon:recon:scans:detail")
    project_id = tables.Column(_project, verbose_name=_("Progetto"))
    # Valore grezzo per lo stato (serve all'auto-refresh e all'icona), mostrato
    # in italiano con display_choices.
    status = tables.Column("status", verbose_name=_("Stato"),
                           status=True,
                           status_choices=STATUS_CHOICES,
                           display_choices=STATUS_DISPLAY)
    phase = tables.Column(_phase, verbose_name=_("Fase"), empty_value="")
    trigger = tables.Column(_trigger, verbose_name=_("Origine"))
    created_at = tables.Column(_created, verbose_name=_("Creata"))

    class Meta(object):
        name = "scans"
        verbose_name = _("Scansioni")
        table_actions = (StartScan,)
        row_actions = (ApriDettaglio, ApriReport)
        row_class = UpdateRow
        status_columns = ("status",)
