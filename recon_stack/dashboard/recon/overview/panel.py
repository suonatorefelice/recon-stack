# Il pannello "Riepilogo" della dashboard recon.
#
# È la pagina d'atterraggio della dashboard (default_panel in dashboard.py):
# riassume l'ultima scansione completata, così chi apre la dashboard vede subito
# lo stato invece di una tabella nuda. Il codice vero sta in views.py e
# summary.py; qui si dichiara solo il pannello.

import horizon
from django.utils.translation import gettext_lazy as _

from recon_stack.dashboard.recon import dashboard


class Overview(horizon.Panel):
    name = _("Riepilogo")
    slug = "overview"
    permissions = ("openstack.roles.admin",)


dashboard.Recon.register(Overview)
