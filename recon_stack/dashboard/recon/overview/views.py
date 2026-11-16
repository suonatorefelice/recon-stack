# La vista del pannello "Riepilogo".
#
# Costruisce il client verso la API /v1, chiama summary.build_summary (logica
# pura, testata sul Mac) e passa al template un contesto già tradotto in
# italiano: i template Django non possono chiamare funzioni Python a piacere,
# quindi arricchiamo qui ogni valore grezzo con la sua etichetta e il colore del
# badge, usando il modulo labels.

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
        for sev in ("high", "medium", "low", "info"):
            counts.append({
                "label": labels.severity_label(sev),
                "css": labels.severity_css(sev),
                "value": data["counts"].get(sev, 0),
            })

        # Segnalazioni più gravi, già tradotte per il template.
        top = []
        for f in data["top_findings"]:
            top.append({
                "severity_it": labels.severity_label(f.get("severity")),
                "severity_css": labels.severity_css(f.get("severity")),
                "type_it": labels.finding_label(f.get("type")),
                "ip_address": f.get("ip_address"),
                "port_number": f.get("port_number"),
                "protocol": f.get("protocol"),
                "message": f.get("message"),
            })

        context["scan"] = scan
        context["counts"] = counts
        context["top_findings"] = top
        context["error"] = data["error"]
        return context
