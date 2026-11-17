# Il pannello "Host": una voce del menu laterale. Il codice vero è in views.py e
# tables.py; qui si dichiara solo il pannello e lo si aggancia alla dashboard.

import horizon
from django.utils.translation import gettext_lazy as _

from recon_stack.dashboard.recon import dashboard


class Hosts(horizon.Panel):
    name = _("Host")
    slug = "hosts"
    permissions = ("openstack.roles.admin",)


dashboard.Recon.register(Hosts)
