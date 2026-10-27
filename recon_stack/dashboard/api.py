# Accesso ai dati per i pannelli Horizon: costruisce il client verso la API /v1.
#
# I pannelli (recon/.../views.py) chiamano reconclient(request) e usano il
# ReconClient già scritto per i comandi `openstack recon` (osc/client.py). Così
# la dashboard non duplica l'accesso ai dati: parla con la stessa API REST,
# riusando lo stesso client.
#
# L'autenticazione viene "in prestito" da Horizon: la richiesta porta già il
# token Keystone dell'utente collegato (request.user.token.id) e il catalogo dei
# servizi, da cui ricaviamo l'indirizzo di recon-api. Lo passiamo all'API nello
# header X-Auth-Token, che keystonemiddleware (davanti a recon-api) sa validare.
#
# Gli import di Horizon/openstack_dashboard sono "pigri" (dentro le funzioni):
# così questo modulo resta importabile e testabile sul Mac, dove Horizon non è
# installato, mentre su DevStack Horizon c'è.

import requests

from recon_stack.osc import client as osc_client


class _TokenSession:
    """Adatta `requests` all'interfaccia che si aspetta ReconClient.

    ReconClient usa session.get(url, params=...).json() e session.post(url,
    json=...).json(), e conta sul fatto che la sessione sollevi un errore sulle
    risposte 4xx/5xx. Qui lo facciamo con `requests`, aggiungendo a ogni
    richiesta il token dell'utente.
    """

    def __init__(self, token, http=None):
        # http si può iniettare nei test; in produzione è una sessione requests.
        self.http = http or requests.Session()
        self.http.headers["X-Auth-Token"] = token

    def get(self, url, params=None):
        response = self.http.get(url, params=params)
        response.raise_for_status()
        return response

    def post(self, url, json=None):
        response = self.http.post(url, json=json)
        response.raise_for_status()
        return response


def wrap(data):
    """Trasforma un dizionario della API in un oggetto con attributi.

    Le tabelle di Horizon leggono i dati per attributo (datum.ip_address) e
    richiedono che ogni riga abbia un campo id: i nostri dizionari /v1 ce
    l'hanno. Un oggetto semplice con gli stessi campi basta allo scopo.
    """
    import types
    return types.SimpleNamespace(**data)


def reconclient(request):
    """Costruisce un ReconClient autenticato come l'utente della richiesta.

    Ricava l'indirizzo di recon-api dal catalogo dei servizi (lo stesso che usa
    la riga di comando) e usa il token dell'utente già collegato a Horizon.
    """
    # Import pigro: disponibile solo dentro Horizon.
    from openstack_dashboard.api import base

    endpoint = base.url_for(request, osc_client.SERVICE_TYPE)
    token = request.user.token.id
    return osc_client.ReconClient(_TokenSession(token), endpoint=endpoint)
