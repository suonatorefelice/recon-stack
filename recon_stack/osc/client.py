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

# Tipo di servizio con cui l'endpoint è registrato nel catalogo Keystone.
SERVICE_TYPE = "recon"


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

    def _get(self, path, **params):
        # Togliamo i parametri non valorizzati: un ?name= vuoto non va mandato.
        clean = {k: v for k, v in params.items() if v is not None}
        # La sessione di keystoneauth1 solleva da sola un errore sulle risposte
        # 4xx/5xx, quindi qui ci fidiamo e leggiamo direttamente il JSON.
        return self.session.get(self._url(path), params=clean).json()

    # --- Scansioni -----------------------------------------------------------

    def list_scans(self, project_id=None, status=None):
        return self._get("/v1/scans", project_id=project_id, status=status)["scans"]

    def get_scan(self, scan_id):
        return self._get(f"/v1/scans/{scan_id}")

    def create_scan(self, project_id):
        return self.session.post(
            self._url("/v1/scans"), json={"project_id": project_id}).json()

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
