# La tabella dei servizi, usata sia nel pannello "Servizi" sia nel dettaglio di
# un host (hosts/views.py la riusa).

from django.utils.translation import gettext_lazy as _
from horizon import tables


class ServicesTable(tables.DataTable):
    host_id = tables.Column("host_id", verbose_name=_("Host"))
    port_number = tables.Column("port_number", verbose_name=_("Porta"))
    protocol = tables.Column("protocol", verbose_name=_("Protocollo"))
    name = tables.Column("name", verbose_name=_("Servizio"), empty_value=_("—"))
    product = tables.Column("product", verbose_name=_("Prodotto"), empty_value=_("—"))
    version = tables.Column("version", verbose_name=_("Versione"), empty_value=_("—"))

    class Meta(object):
        name = "services"
        verbose_name = _("Servizi")
