# Vista del pannello "Riepilogo": chiama summary.build_summary (logica pura) e
# passa al template un contesto già tradotto in italiano (i template Django non
# chiamano funzioni Python, quindi arricchiamo qui etichette e colori con labels).

from django.utils.translation import gettext_lazy as _
from django.views import generic

from recon_stack.dashboard import api
from recon_stack.dashboard.recon import labels
from recon_stack.dashboard.recon.overview import summary


class IndexView(generic.TemplateView):
    template_name = "recon/overview/index.html"
    page_title = _("Riepilogo")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = api.reconclient(self.request)
        # build_summary restituisce la scansione già arricchita (etichette
        # italiane, UUID accorciati, date leggibili): la passiamo così com'è.
        data = summary.build_summary(client)
        scan = data["scan"]

        # Conteggi per gravità con etichetta e colore, nell'ordine grave→info.
        counts = []
        for sev in labels.SEVERITIES:
            counts.append({
                "label": labels.severity_label(sev),
                "css": labels.severity_css(sev),
                "value": data["counts"].get(sev, 0),
            })

        # Segnalazioni più gravi, già tradotte per il template.
        top = [labels.enrich_finding(f) for f in data["top_findings"]]

        context["scan"] = scan
        context["counts"] = counts
        context["top_findings"] = top
        context["error"] = data["error"]
        # Breadcrumb: Horizon legge page_title dal contesto, e
        # generic.TemplateView non ce lo mette da sé.
        context["page_title"] = self.page_title
        return context
