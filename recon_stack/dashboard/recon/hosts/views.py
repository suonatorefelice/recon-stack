# Viste del pannello "Host": l'elenco (DataTableView) e il dettaglio (campi
# dell'host più la tabella dei suoi servizi). I dati vengono dalla API /v1.

from django.utils.translation import gettext_lazy as _
from horizon import exceptions
from horizon import tables as horizon_tables

from recon_stack.dashboard import api
from recon_stack.dashboard.recon import labels
from recon_stack.dashboard.recon.hosts import tables as hosts_tables
from recon_stack.dashboard.recon.services import tables as services_tables


class IndexView(horizon_tables.DataTableView):
    table_class = hosts_tables.HostsTable
    template_name = "recon/hosts/index.html"
    page_title = _("Host")

    def get_data(self):
        # Host di una scansione precisa (?scan_id=); senza parametro vale il
        # default della API (l'ultima completata), lo stesso del Riepilogo.
        scan_id = self.request.GET.get("scan_id") or None
        try:
            hosts = api.reconclient(self.request).list_hosts(scan_id=scan_id)
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
        # Arricchiamo l'host con l'etichetta della classificazione (stessa mappa
        # della tabella) e gli UUID accorciati, pronti per il template.
        host = dict(self._get_host())
        if host:
            host["classification_it"] = labels.classification_label(
                host.get("classification"))
            host["network_short"] = labels.short_uuid(host.get("network_id"))
            host["port_short"] = labels.short_uuid(host.get("neutron_port_id"))
        context["host"] = api.wrap(host)
        return context
