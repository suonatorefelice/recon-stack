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
    # Campo di partenza: l'id del progetto incollato a mano. Se riusciamo a
    # leggere l'elenco dei progetti da Keystone, in __init__ lo sostituiamo con
    # un menu a tendina (più comodo e meno soggetto a errori di battitura).
    project_id = forms.CharField(
        label=_("Id progetto"), max_length=64,
        help_text=_("Id del progetto OpenStack da scansionare."))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._usa_elenco_progetti()

    def _usa_elenco_progetti(self):
        """Prova a trasformare project_id in un menu con i progetti di Keystone.

        Import pigro: openstack_dashboard esiste solo dentro Horizon (non sul
        Mac). Se Keystone non risponde o non ci sono progetti, teniamo il campo
        di testo: un problema dell'elenco non deve impedire di avviare una
        scansione.
        """
        try:
            from openstack_dashboard.api import keystone
            progetti, _altri = keystone.tenant_list(self.request)
            scelte = [(p.id, getattr(p, "name", p.id)) for p in progetti]
            if not scelte:
                return
            self.fields["project_id"] = forms.ChoiceField(
                label=_("Progetto"),
                choices=scelte,
                help_text=_("Progetto OpenStack da scansionare."))
        except Exception:
            # Teniamo il CharField: l'utente incolla l'id a mano.
            pass

    def handle(self, request, data):
        try:
            scan = api.reconclient(request).create_scan(data["project_id"])
        except Exception:
            # Horizon mostra l'errore e riapre il modulo.
            raise
        messages.success(
            request, _("Scansione avviata (id %s).") % scan.get("id"))
        return True
