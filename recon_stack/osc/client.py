# Client HTTP minimale verso la API REST /v1 di Recon-Stack.
#
# I comandi "openstack recon ..." (commands.py) non parlano col database: parlano
# con la nostra API via HTTP, come farebbe qualsiasi altro client. Questo client
# usa la "sessione" dell'OpenStackClient, cioè l'oggetto che porta già con sé il
# token Keystone del chiamante e sa come firmare le richieste: così i comandi
# ereditano l'autenticazione dell'utente che ha lanciato `openstack` (ADR 0002).
#
# L'indirizzo dell'API non è scritto a mano: lo si chiede al catalogo di Keystone
# (service type "recon", che il plugin DevStack registra). Così lo stesso comando
# funziona su qualsiasi DevStack senza configurare URL.
#
# Il client non dipende da Flask né dal database: riceve una "sessione" che
# espone get() e post() (quella di keystoneauth1). Nei test gliene passiamo una
# finta, così si prova senza un vero Keystone.

from osc_lib import exceptions

# Tipo di servizio con cui l'endpoint è registrato nel catalogo Keystone.
SERVICE_TYPE = "recon"


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
    """Chiama la API /v1 usando la sessione (e quindi il token) del chiamante."""

    def __init__(self, session, endpoint=None, interface="public",
                 region_name=None):
        self.session = session
        # Se l'endpoint non è dato lo ricaviamo dal catalogo alla prima richiesta
        # (endpoint property): evitiamo di interrogare Keystone se non serve.
        self._endpoint = endpoint
        self._interface = interface
        self._region_name = region_name

    @property
    def endpoint(self):
        """Indirizzo base dell'API, dal catalogo Keystone (una volta sola)."""
        if self._endpoint is None:
            self._endpoint = self.session.get_endpoint(
                service_type=SERVICE_TYPE,
                interface=self._interface,
                region_name=self._region_name)
        return self._endpoint

    def _url(self, path):
        return self.endpoint.rstrip("/") + path

    def _call(self, method, path, **kwargs):
        """Esegue una richiesta e restituisce il JSON della risposta.

        raise_exc=False: la sessione di keystoneauth1, sugli errori 4xx/5xx,
        solleverebbe da sola un'eccezione cercando il messaggio nel formato
        degli altri componenti OpenStack; il nostro formato è diverso e
        l'utente vedeva solo "Unrecognized schema in response body" (trovato
        nel test su DevStack, con il limite di frequenza). Leggiamo noi
        l'errore e lo mostriamo così com'è scritto dalla API.
        """
        response = getattr(self.session, method)(
            self._url(path), raise_exc=False, **kwargs)
        if response.status_code >= 400:
            raise exceptions.CommandError(
                f"{_error_message(response)} (HTTP {response.status_code})")
        return response.json()

    def _get(self, path, **params):
        # Togliamo i parametri non valorizzati: un ?name= vuoto non va mandato.
        clean = {k: v for k, v in params.items() if v is not None}
        return self._call("get", path, params=clean)

    # --- Scansioni -----------------------------------------------------------

    def list_scans(self, project_id=None, status=None):
        return self._get("/v1/scans", project_id=project_id, status=status)["scans"]

    def get_scan(self, scan_id):
        return self._get(f"/v1/scans/{scan_id}")

    def get_scan_diff(self, scan_id):
        return self._get(f"/v1/scans/{scan_id}/diff")

    def get_scan_exposure(self, scan_id, severity=None):
        return self._get(f"/v1/scans/{scan_id}/exposure",
                         severity=severity)["findings"]

    def create_scan(self, project_id):
        return self._call("post", "/v1/scans", json={"project_id": project_id})

    # --- Host ----------------------------------------------------------------

    def list_hosts(self, project_id=None, scan_id=None, classification=None):
        return self._get("/v1/hosts", project_id=project_id, scan_id=scan_id,
                         classification=classification)["hosts"]

    def get_host(self, host_id):
        return self._get(f"/v1/hosts/{host_id}")

    # --- Servizi -------------------------------------------------------------

    def list_services(self, project_id=None, scan_id=None, name=None):
        return self._get("/v1/services", project_id=project_id, scan_id=scan_id,
                         name=name)["services"]
