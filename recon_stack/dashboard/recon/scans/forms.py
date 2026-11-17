# Modulo "Avvia scansione": chiede il progetto e fa la POST /v1/scans. In una
# SelfHandlingForm di Horizon handle() parte all'invio. Le regole (admin,
# frequenza) le applica la API; se rifiuta, mostriamo il suo messaggio.

from django.utils.translation import gettext_lazy as _
from horizon import exceptions
from horizon import forms
from horizon import messages

from recon_stack.dashboard import api
from recon_stack.dashboard.recon.scans import progetti as progetti_sel


class StartScanForm(forms.SelfHandlingForm):
    # Il campo nasce come testo libero per l'id; se Keystone risponde, in
    # __init__ diventa un menu a tendina con i progetti.
    project_id = forms.CharField(
        label=_("Id progetto"), max_length=64,
        help_text=_("Id del progetto OpenStack da scansionare."))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._usa_elenco_progetti()

    def _usa_elenco_progetti(self):
        """Trasforma project_id in un menu coi progetti scansionabili di Keystone.

        Mostra solo i progetti consentiti (di norma recon-demo; filtro in
        progetti.scelte_menu, elenco in RECON_SCANNABLE_PROJECTS). Import pigro
        (Horizon non c'è sul Mac); se Keystone non risponde teniamo il campo di
        testo, così un problema dell'elenco non blocca l'avvio.
        """
        try:
            from django.conf import settings
            from openstack_dashboard.api import keystone
            progetti, _altri = keystone.tenant_list(self.request)
            consentiti = getattr(
                settings, "RECON_SCANNABLE_PROJECTS",
                progetti_sel.PROGETTI_SCANSIONABILI_DEFAULT)
            scelte = progetti_sel.scelte_menu(progetti, consentiti)
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
            # Con un messaggio, Horizon tratta l'errore come recuperabile: lo
            # mostra insieme al dettaglio della API (es. "riprovare fra 42 s")
            # invece di rispondere 500. return False riapre il modulo.
            exceptions.handle(request, _("Scansione non avviata."))
            return False
        messages.success(
            request, _("Scansione avviata (id %s).") % scan.get("id"))
        return True
