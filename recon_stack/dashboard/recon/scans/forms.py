# Il modulo "Avvia scansione": chiede l'id del progetto e chiama la API.
#
# Una SelfHandlingForm di Horizon è un form che sa gestirsi da solo: quando
# l'utente lo invia, Horizon chiama handle(), che qui fa la POST /v1/scans
# tramite il client. Le regole (ruolo admin, limite di frequenza) le applica la
# API; se rifiuta, il client solleva un errore e Horizon mostra il messaggio.

from django.utils.translation import gettext_lazy as _
from horizon import forms
from horizon import messages

from recon_stack.dashboard import api


class StartScanForm(forms.SelfHandlingForm):
    project_id = forms.CharField(
        label=_("Id progetto"), max_length=64,
        help_text=_("Id del progetto OpenStack da scansionare."))

    def handle(self, request, data):
        try:
            scan = api.reconclient(request).create_scan(data["project_id"])
        except Exception:
            # Horizon mostra l'errore e riapre il modulo.
            raise
        messages.success(
            request, _("Scansione avviata (id %s).") % scan.get("id"))
        return True
