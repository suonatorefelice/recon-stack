# Le viste del pannello "Scansioni": elenco, dettaglio e avvio.

from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views import generic
from horizon import exceptions
from horizon import forms as horizon_forms
from horizon import tables as horizon_tables

from recon_stack.dashboard import api
from recon_stack.dashboard.recon.scans import forms as scans_forms
from recon_stack.dashboard.recon.scans import tables as scans_tables


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
        client = api.reconclient(self.request)
        try:
            scan = client.get_scan(self.kwargs["scan_id"])
        except Exception:
            exceptions.handle(self.request,
                              _("Impossibile leggere la scansione dalla API."))
            scan = {}
        context["scan"] = api.wrap(scan) if scan else None
        # Diff con la scansione precedente (Step 10); se fallisce non blocca la
        # pagina, mostriamo solo i dati della scansione.
        try:
            context["diff"] = client.get_scan_diff(self.kwargs["scan_id"])
        except Exception:
            context["diff"] = None
        # Segnalazioni di esposizione (Step 11); stesso criterio: se fallisce
        # mostriamo comunque il resto della pagina.
        try:
            context["findings"] = client.get_scan_exposure(self.kwargs["scan_id"])
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
