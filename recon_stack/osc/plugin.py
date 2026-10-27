# Aggancio del plugin all'OpenStackClient (Step 8).
#
# L'OpenStackClient, quando parte, cerca i plugin dichiarati nell'entry point
# "openstack.cli.extension" (vedi setup.cfg) e, per ognuno, legge da questo
# modulo alcune costanti e la funzione make_client. Da quel momento `openstack`
# espone un client in più, raggiungibile nei comandi come
# self.app.client_manager.recon.
#
# Le costanti sotto seguono la convenzione dell'OpenStackClient:
#   API_NAME            il nome con cui il client è esposto (client_manager.recon)
#   API_VERSION_OPTION  l'opzione per scegliere la versione dell'API
#   API_VERSIONS        le versioni disponibili e la classe client di ognuna

from recon_stack.osc import client

API_NAME = "recon"
API_VERSION_OPTION = "os_recon_api_version"
DEFAULT_API_VERSION = "1"
API_VERSIONS = {
    "1": "recon_stack.osc.client.ReconClient",
}


def make_client(instance):
    """Costruisce il ReconClient a partire dal client manager dell'OpenStackClient.

    instance porta con sé la sessione autenticata (instance.session) e le
    preferenze dell'utente (interface pubblica/interna, regione): le passiamo al
    client, che le userà per trovare l'endpoint nel catalogo e firmare le
    richieste.
    """
    return client.ReconClient(
        session=instance.session,
        interface=instance.interface,
        region_name=instance.region_name)


def build_option_parser(parser):
    """Punto in cui un plugin aggiungerebbe opzioni globali a `openstack`.

    Non ci servono opzioni globali, ma la funzione deve esistere e restituire il
    parser: l'OpenStackClient la chiama comunque.
    """
    return parser
