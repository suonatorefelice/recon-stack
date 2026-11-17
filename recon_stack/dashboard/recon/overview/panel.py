# Il pannello "Riepilogo": pagina d'atterraggio (default_panel), riassume
# l'ultima scansione completata. Codice vero in views.py e summary.py.

import horizon
from django.utils.translation import gettext_lazy as _

from recon_stack.dashboard.recon import dashboard


class Overview(horizon.Panel):
    name = _("Riepilogo")
    slug = "overview"
    permissions = ("openstack.roles.admin",)


dashboard.Recon.register(Overview)
