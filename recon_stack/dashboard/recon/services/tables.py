# La tabella dei servizi, usata sia nel pannello "Servizi" sia nel dettaglio di
# un host (hosts/views.py la riusa).

from django.utils.translation import gettext_lazy as _
from horizon import tables


VIEWS = {
    "internal": _("interna"),
    "external": _("esterna (floating IP)"),
}


def _view(service):
    return VIEWS.get(service.view, service.view)


class ServicesTable(tables.DataTable):
    # L'indirizzo IP invece dell'id dell'host: è ciò che serve a chi legge.
    ip_address = tables.Column("ip_address", verbose_name=_("Indirizzo IP"))
    port_number = tables.Column("port_number", verbose_name=_("Porta"))
    protocol = tables.Column("protocol", verbose_name=_("Protocollo"))
    name = tables.Column("name", verbose_name=_("Servizio"), empty_value=_("—"))
    product = tables.Column("product", verbose_name=_("Prodotto"), empty_value=_("—"))
    version = tables.Column("version", verbose_name=_("Versione"), empty_value=_("—"))
    # Lo stesso servizio può comparire due volte, visto dall'interno della rete
    # e dall'esterno sul floating IP: la colonna dice quale delle due.
    view = tables.Column(_view, verbose_name=_("Vista"))

    class Meta(object):
        name = "services"
        verbose_name = _("Servizi")
