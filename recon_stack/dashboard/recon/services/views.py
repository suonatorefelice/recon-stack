# Vista del pannello "Servizi": elenco del catalogo con ricerca per nome. Il
# campo di ricerca invia ?name=..., che passiamo alla API (il filtro vero è lì).

from django.utils.translation import gettext_lazy as _
from horizon import exceptions
from horizon import tables as horizon_tables

from recon_stack.dashboard import api
from recon_stack.dashboard.recon.services import tables as services_tables


class IndexView(horizon_tables.DataTableView):
    table_class = services_tables.ServicesTable
    template_name = "recon/services/index.html"
    page_title = _("Servizi")

    def get_data(self):
        name = self.request.GET.get("name") or None
        # Servizi di una scansione precisa (?scan_id=); senza parametro vale il
        # default della API (l'ultima completata), lo stesso del Riepilogo.
        scan_id = self.request.GET.get("scan_id") or None
        try:
            services = api.reconclient(self.request).list_services(
                scan_id=scan_id, name=name)
        except Exception:
            exceptions.handle(self.request,
                              _("Impossibile leggere i servizi dalla API."))
            return []
        return [api.wrap(s) for s in services]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Rimanda il testo cercato al campo di ricerca, così resta scritto.
        context["search_name"] = self.request.GET.get("name", "")
        return context
