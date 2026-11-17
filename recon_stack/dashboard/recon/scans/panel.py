# Il pannello "Scansioni" della dashboard recon.

import horizon
from django.utils.translation import gettext_lazy as _

from recon_stack.dashboard.recon import dashboard


class Scans(horizon.Panel):
    name = _("Scansioni")
    slug = "scans"
    permissions = ("openstack.roles.admin",)


dashboard.Recon.register(Scans)
