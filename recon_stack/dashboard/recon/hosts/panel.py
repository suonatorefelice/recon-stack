# Il pannello "Host" della dashboard recon.
#
# Un Panel è una voce nel menu laterale della dashboard. Il codice vero (cosa
# mostra) sta in views.py e tables.py; qui si dichiara solo il pannello e lo si
# aggancia alla dashboard Recon.

import horizon
from django.utils.translation import gettext_lazy as _

from recon_stack.dashboard.recon import dashboard


class Hosts(horizon.Panel):
    name = _("Host")
    slug = "hosts"
    permissions = ("openstack.roles.admin",)


dashboard.Recon.register(Hosts)
