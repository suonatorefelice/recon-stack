# Le viste del pannello "Scansioni": elenco, dettaglio e avvio.

from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views import generic
from horizon import exceptions
from horizon import forms as horizon_forms
from horizon import tables as horizon_tables

from recon_stack.dashboard import api
from recon_stack.dashboard.recon import labels
from recon_stack.dashboard.recon.scans import forms as scans_forms
from recon_stack.dashboard.recon.scans import tables as scans_tables
from recon_stack.db import models


class IndexView(horizon_tables.DataTableView):
    table_class = scans_tables.ScansTable
    template_name = "recon/scans/index.html"
    page_title = _("Scansioni")

    def get_data(self):
        try:
            scans = api.reconclient(self.request).list_scans()
        except Exception:
            exceptions.handle(self.request,
                              _("Impossibile leggere le scansioni dalla API."))
            return []
        return [api.wrap(s) for s in scans]


class DetailView(generic.TemplateView):
    template_name = "recon/scans/detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Ultima briciola del breadcrumb: Horizon ci mette context["page_title"]
        # (templatetag breadcrumb_nav). Senza, mostrava "None". Usiamo l'id
        # accorciato della scansione, così la briciola la identifica; lo
        # ricaviamo dall'URL, quindi è sempre presente anche se l'API non
        # risponde. Il titolo della pagina resta "Dettaglio scansione" (lo fissa
        # il template nel blocco page_header).
        context["page_title"] = labels.short_uuid(self.kwargs["scan_id"])
        client = api.reconclient(self.request)
        try:
            scan = client.get_scan(self.kwargs["scan_id"])
        except Exception:
            exceptions.handle(self.request,
                              _("Impossibile leggere la scansione dalla API."))
            scan = {}
        # Arricchiamo la scansione con le etichette italiane e gli UUID
        # accorciati: i template Django non possono chiamare le funzioni di
        # labels da soli, quindi prepariamo qui i campi pronti da mostrare.
        if scan:
            scan = dict(scan)
            scan["status_it"] = labels.status_label(scan.get("status"))
            scan["trigger_it"] = labels.trigger_label(scan.get("trigger"))
            scan["id_short"] = labels.short_uuid(scan.get("id"))
            scan["project_short"] = labels.short_uuid(scan.get("project_id"))
            scan["created_h"] = labels.human_datetime(scan.get("created_at"))
            scan["started_h"] = labels.human_datetime(scan.get("started_at"))
            scan["finished_h"] = labels.human_datetime(scan.get("finished_at"))
            # Avanzamento: la fase leggibile ("Scoperta... (3 di 6)") e un flag
            # "in corso" (PENDING/RUNNING), con cui il template mostra la rotella
            # e si auto-ricarica finché la scansione non è finita.
            scan["phase_text"] = labels.phase_text(scan.get("phase"))
            scan["in_corso"] = scan.get("status") in (
                models.SCAN_PENDING, models.SCAN_RUNNING)
        context["scan"] = api.wrap(scan) if scan else None
        # Diff con la scansione precedente (Step 10); se fallisce non blocca la
        # pagina, mostriamo solo i dati della scansione.
        try:
            context["diff"] = client.get_scan_diff(self.kwargs["scan_id"])
        except Exception:
            context["diff"] = None
        # Segnalazioni di esposizione (Step 11); stesso criterio: se fallisce
        # mostriamo comunque il resto della pagina. Ogni segnalazione viene
        # tradotta (gravità, colore del badge, tipo) per il template.
        try:
            raw = client.get_scan_exposure(self.kwargs["scan_id"])
            findings = []
            for f in raw:
                f = dict(f)
                f["severity_it"] = labels.severity_label(f.get("severity"))
                f["severity_css"] = labels.severity_css(f.get("severity"))
                f["type_it"] = labels.finding_label(f.get("type"))
                findings.append(api.wrap(f))
            context["findings"] = findings
        except Exception:
            context["findings"] = None
        return context


class StartScanView(horizon_forms.ModalFormView):
    form_class = scans_forms.StartScanForm
    template_name = "recon/scans/start.html"
    submit_url = reverse_lazy("horizon:recon:scans:start")
    success_url = reverse_lazy("horizon:recon:scans:index")
    modal_header = _("Avvia scansione")
    page_title = _("Avvia scansione")
