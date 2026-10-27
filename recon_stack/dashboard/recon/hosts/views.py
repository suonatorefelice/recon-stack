# Le viste del pannello "Host": elenco e dettaglio.
#
# Una vista di Horizon prende i dati (qui dalla API /v1 tramite il client) e li
# passa a una tabella o a un template. L'elenco usa una DataTableView, che
# disegna la tabella da sola; il dettaglio mostra i campi dell'host e, sotto, la
# tabella dei servizi trovati su di esso.

from django.utils.translation import gettext_lazy as _
from horizon import exceptions
from horizon import tables as horizon_tables

from recon_stack.dashboard import api
from recon_stack.dashboard.recon.hosts import tables as hosts_tables
from recon_stack.dashboard.recon.services import tables as services_tables


class IndexView(horizon_tables.DataTableView):
    table_class = hosts_tables.HostsTable
    template_name = "recon/hosts/index.html"
    page_title = _("Host")

    def get_data(self):
        # Filtro opzionale per classificazione, passato come ?classification=.
        classification = self.request.GET.get("classification") or None
        try:
            hosts = api.reconclient(self.request).list_hosts(
                classification=classification)
        except Exception:
            exceptions.handle(self.request,
                              _("Impossibile leggere gli host dalla API."))
            return []
        return [api.wrap(h) for h in hosts]


class DetailView(horizon_tables.DataTableView):
    # La tabella del dettaglio è quella dei servizi dell'host.
    table_class = services_tables.ServicesTable
    template_name = "recon/hosts/detail.html"
    page_title = _("Dettaglio host")

    def _get_host(self):
        # Letto una volta sola e riusato (dati e contesto del template).
        if not hasattr(self, "_host"):
            try:
                self._host = api.reconclient(self.request).get_host(
                    self.kwargs["host_id"])
            except Exception:
                exceptions.handle(self.request,
                                  _("Impossibile leggere l'host dalla API."))
                self._host = {}
        return self._host

    def get_data(self):
        return [api.wrap(s) for s in self._get_host().get("services", [])]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["host"] = api.wrap(self._get_host())
        return context
