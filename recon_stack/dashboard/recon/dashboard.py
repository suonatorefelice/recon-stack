# La dashboard "Recon-Stack" dentro Horizon (ADR 0010).
#
# Una Dashboard di Horizon è una voce del menu principale che raggruppa dei
# pannelli. Qui dichiariamo la nostra, con i tre pannelli dello Step 9, e la
# registriamo. L'accesso è riservato agli admin (permissions), coerente con la
# API /v1 (ADR 0002).

import horizon
from django.utils.translation import gettext_lazy as _


class Recon(horizon.Dashboard):
    name = _("Recon-Stack")
    slug = "recon"
    # I pannelli della dashboard, nell'ordine del menu. Ogni nome corrisponde a
    # una sottocartella con un panel.py (overview/, hosts/, services/, scans/).
    # "Riepilogo" è la pagina d'atterraggio: chi apre la dashboard vede subito
    # lo stato dell'ultima scansione invece della tabella host nuda.
    panels = ("overview", "hosts", "services", "scans")
    default_panel = "overview"
    # Solo chi ha il ruolo admin vede ed apre la dashboard.
    permissions = ("openstack.roles.admin",)


horizon.register(Recon)
