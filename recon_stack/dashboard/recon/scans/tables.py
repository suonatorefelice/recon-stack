# La tabella delle scansioni (storico) e l'azione "Avvia scansione".

from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from horizon import tables

from recon_stack.dashboard import api
from recon_stack.dashboard.recon import labels


# Funzioni di cella: estraggono il campo grezzo dalla riga e lo traducono con il
# modulo labels. La colonna "id" mostra l'UUID accorciato, ma il collegamento al
# dettaglio continua a usare l'id pieno della riga (Horizon risolve il link
# dall'id dell'oggetto, non dal testo mostrato).
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
# riga finché non diventano finali, aggiornando stato e fase senza ricaricare.
STATUS_CHOICES = (
    ("done", True),
    ("failed", False),
    ("rejected", False),
)


class StartScan(tables.LinkAction):
    """Pulsante che apre il modulo per avviare una nuova scansione."""

    name = "start"
    verbose_name = _("Avvia scansione")
    url = "horizon:recon:scans:start"
    classes = ("ajax-modal",)   # apre il form in una finestra modale
    icon = "plus"
    # Solo admin può avviare scansioni (ADR 0002); la API lo impone comunque.
    policy_rules = ()


class ApriDettaglio(tables.LinkAction):
    """Pulsante in fondo alla riga che apre il dettaglio di una scansione.

    Il dettaglio (fasi, segnalazioni di esposizione, diff) è già raggiungibile
    cliccando l'ID accorciato, ma come link è poco evidente. Questo pulsante
    rende il collegamento esplicito, utile soprattutto a scansione finita per
    andare subito al riepilogo di quella scansione. Resta visibile anche mentre
    la scansione è in corso: la pagina di dettaglio mostra fase e avanzamento.
    """

    name = "detail"
    verbose_name = _("Dettaglio")
    url = "horizon:recon:scans:detail"

    def get_link_url(self, datum):
        # datum è la scansione (SimpleNamespace con .id): costruiamo l'URL del
        # dettaglio con l'id pieno, non con quello accorciato mostrato in tabella.
        return reverse(self.url, args=[datum.id])


class UpdateRow(tables.Row):
    """Rilegge una singola scansione dalla API per l'auto-aggiornamento.

    Con ajax=True Horizon, per le righe in stato non finale, richiama da sola
    get_data ogni pochi secondi e riscrive la riga: così stato e fase di una
    scansione in corso avanzano nell'elenco senza ricaricare la pagina.
    """

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
        row_actions = (ApriDettaglio,)
        row_class = UpdateRow
        status_columns = ("status",)
