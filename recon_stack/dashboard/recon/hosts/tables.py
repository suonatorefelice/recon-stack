# La tabella degli host, mostrata nel pannello "Host".
#
# Una DataTable di Horizon descrive le colonne di una tabella; Horizon la
# disegna, con intestazioni, ordinamento e ricerca. I dati (una riga per host)
# li fornisce la vista (views.py); ogni riga è un oggetto con gli attributi
# indicati come prima parola di ogni Column.

from django.utils.translation import gettext_lazy as _
from horizon import tables


# Etichette leggibili per la classificazione (il valore grezzo è in inglese,
# come nel database: known/unknown/absent).
CLASSIFICATIONS = {
    "known": _("censito"),
    "unknown": _("sconosciuto"),
    "absent": _("assente"),
}


def _classification(host):
    return CLASSIFICATIONS.get(host.classification, host.classification)


class HostsTable(tables.DataTable):
    # L'IP è un collegamento al dettaglio dell'host (hosts/<id>/).
    ip_address = tables.Column(
        "ip_address", verbose_name=_("Indirizzo IP"),
        link="horizon:recon:hosts:detail")
    classification = tables.Column(
        _classification, verbose_name=_("Classificazione"))
    server_name = tables.Column(
        "server_name", verbose_name=_("VM"),
        empty_value=_("—"))
    network_id = tables.Column(
        "network_id", verbose_name=_("Rete"), empty_value=_("—"))

    class Meta(object):
        name = "hosts"
        verbose_name = _("Host")
