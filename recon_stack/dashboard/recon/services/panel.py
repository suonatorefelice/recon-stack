# Il pannello "Servizi" della dashboard recon.

import horizon
from django.utils.translation import gettext_lazy as _

from recon_stack.dashboard.recon import dashboard


class Services(horizon.Panel):
    name = _("Servizi")
    slug = "services"
    permissions = ("openstack.roles.admin",)


dashboard.Recon.register(Services)
