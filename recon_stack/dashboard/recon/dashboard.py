# La dashboard "Recon-Stack" dentro Horizon (ADR 0010): una voce di menu che
# raggruppa i pannelli, riservata agli admin come la API /v1 (ADR 0002).

import horizon
from django.utils.translation import gettext_lazy as _


class Recon(horizon.Dashboard):
    name = _("Recon-Stack")
    slug = "recon"
    # Pannelli nell'ordine del menu (ogni nome è una sottocartella con panel.py);
    # "overview" (Riepilogo) è la pagina d'atterraggio.
    panels = ("overview", "hosts", "services", "scans")
    default_panel = "overview"
    permissions = ("openstack.roles.admin",)  # solo admin


horizon.register(Recon)
