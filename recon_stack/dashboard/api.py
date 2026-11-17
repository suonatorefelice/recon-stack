# Accesso ai dati per i pannelli Horizon. Qui vive anche il client HTTP verso la
# API /v1 (ReconClient): la dashboard è l'unico client, quindi non serve un
# modulo a parte. L'autenticazione è "in prestito" da Horizon: usiamo il token
# dell'utente collegato (X-Auth-Token) e l'indirizzo di recon-api dal catalogo.
# Gli import di Horizon sono "pigri" (dentro le funzioni), così il modulo resta
# importabile e testabile sul Mac. ReconClient non dipende da Horizon: riceve
# endpoint e sessione già pronti (nei test una sessione finta).

import types

import requests

# Tipo di servizio con cui il plugin DevStack registra recon-api nel catalogo.
_SERVICE_TYPE = "recon"

# Secondi massimi per ogni richiesta a recon-api (un worker Horizon non resta appeso).
_HTTP_TIMEOUT = 10


class ReconClientError(Exception):
    """Errore restituito dalla API di Recon-Stack (HTTP 4xx/5xx)."""


def _error_message(response):
    """Il messaggio d'errore della nostra API, es. "ruolo 'admin' richiesto".

    La API risponde agli errori con {"error": "..."} (api/app.py). Se il corpo
    non è in quel formato (ad esempio un errore di un proxy), usiamo il testo.
    """
    try:
        return response.json().get("error") or response.text
    except ValueError:
        return response.text


class ReconClient:
    """Chiama la API /v1 usando la sessione (e quindi il token) del chiamante.

    La sessione espone get() e post() e restituisce una risposta con
    status_code, json() e text; nei test ne passiamo una finta.
    """

    def __init__(self, session, endpoint):
        self.session = session
        self.endpoint = endpoint.rstrip("/")

    def _request(self, method, path, **kwargs):
        """Esegue la richiesta e la restituisce, o solleva l'errore.

        Leggiamo noi l'errore (status >= 400) e lo mostriamo com'è scritto dalla
        nostra API, invece del messaggio generico di altri client HTTP.
        """
        response = getattr(self.session, method)(self.endpoint + path, **kwargs)
        if response.status_code >= 400:
            raise ReconClientError(
                f"{_error_message(response)} (HTTP {response.status_code})")
        return response

    def _call(self, method, path, **kwargs):
        return self._request(method, path, **kwargs).json()

    @staticmethod
    def _clean(params):
        # Togliamo i parametri non valorizzati: un ?name= vuoto non va mandato.
        return {k: v for k, v in params.items() if v is not None}

    def _get(self, path, **params):
        return self._call("get", path, params=self._clean(params))

    # --- Scansioni -----------------------------------------------------------

    def list_scans(self, status=None):
        return self._get("/v1/scans", status=status)["scans"]

    def get_scan(self, scan_id):
        return self._get(f"/v1/scans/{scan_id}")

    def get_scan_diff(self, scan_id):
        return self._get(f"/v1/scans/{scan_id}/diff")

    def get_scan_exposure(self, scan_id):
        return self._get(f"/v1/scans/{scan_id}/exposure")["findings"]

    def create_scan(self, project_id):
        return self._call("post", "/v1/scans", json={"project_id": project_id})

    # --- Host ----------------------------------------------------------------

    def list_hosts(self, scan_id=None):
        return self._get("/v1/hosts", scan_id=scan_id)["hosts"]

    def get_host(self, host_id):
        return self._get(f"/v1/hosts/{host_id}")

    # --- Servizi -------------------------------------------------------------

    def list_services(self, scan_id=None, name=None):
        return self._get("/v1/services", scan_id=scan_id, name=name)["services"]


class _TokenSession:
    """Adatta `requests` all'interfaccia di ReconClient (get/post), aggiungendo
    a ogni richiesta il token dell'utente. Non solleva sugli errori HTTP: li
    legge ReconClient dallo status."""

    def __init__(self, token, http=None):
        # http si può iniettare nei test; in produzione è una sessione requests.
        self.http = http or requests.Session()
        self.http.headers["X-Auth-Token"] = token

    def get(self, url, params=None):
        return self.http.get(url, params=params, timeout=_HTTP_TIMEOUT)

    def post(self, url, json=None):
        return self.http.post(url, json=json, timeout=_HTTP_TIMEOUT)


def wrap(data):
    """Dizionario della API -> oggetto con attributi (le tabelle Horizon leggono
    datum.ip_address e vogliono un campo id, che i nostri dizionari /v1 hanno)."""
    return types.SimpleNamespace(**data)


def reconclient(request):
    """Costruisce un ReconClient autenticato come l'utente della richiesta.

    Ricava l'indirizzo di recon-api dal catalogo dei servizi e inoltra il token
    dell'utente collegato a Horizon: la API controlla il ruolo admin su chi sta
    davvero usando la dashboard, non su un account di servizio.
    """
    # Import pigro: disponibile solo dentro Horizon.
    from openstack_dashboard.api import base

    endpoint = base.url_for(request, _SERVICE_TYPE)
    token = request.user.token.id
    return ReconClient(_TokenSession(token), endpoint)
