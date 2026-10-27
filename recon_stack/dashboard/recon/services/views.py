# La vista del pannello "Servizi": elenco con ricerca per nome.
#
# Mostra i servizi del catalogo (ultima scansione completata). Un campo di
# ricerca nel template invia ?name=... e qui filtriamo chiamando la API con quel
# nome (la API fa il filtro vero, api/v1.py).

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
        try:
            services = api.reconclient(self.request).list_services(name=name)
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
