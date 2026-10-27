# Test tempest del percorso completo di Recon-Stack (step 13).
#
# Prova il servizio su un DevStack vero, dall'esterno, via API REST, come farebbe
# un utente: chiede una scansione del progetto demo, aspetta che finisca e
# controlla che i risultati ci siano (host, servizi e le segnalazioni di
# esposizione dovute alle regole volutamente sbagliate del demo).
#
# Si esegue su DevStack dopo aver installato il plugin e creato il progetto demo
# (demo/setup_demo.sh). Non gira sul Mac: ha bisogno di tempest e di OpenStack.

from tempest import config
from tempest.lib.common import rest_client
from tempest.lib.common.utils import test_utils
from tempest.lib import decorators
import tempest.test

CONF = config.CONF


class ReconClient(rest_client.RestClient):
    """Client REST minimale verso recon-api, per i test tempest.

    tempest costruisce il client con l'autenticazione dell'utente; qui aggiungiamo
    solo i metodi che servono ai test. Il service type nel catalogo è "recon".
    """

    def create_scan(self, project_id):
        resp, body = self.post("v1/scans",
                               self._json({"project_id": project_id}))
        self.expected_success(202, resp.status)
        return self._parse(body)

    def get_scan(self, scan_id):
        resp, body = self.get(f"v1/scans/{scan_id}")
        self.expected_success(200, resp.status)
        return self._parse(body)

    def list_hosts(self, scan_id):
        resp, body = self.get(f"v1/hosts?scan_id={scan_id}")
        self.expected_success(200, resp.status)
        return self._parse(body)["hosts"]

    def get_exposure(self, scan_id):
        resp, body = self.get(f"v1/scans/{scan_id}/exposure")
        self.expected_success(200, resp.status)
        return self._parse(body)["findings"]

    @staticmethod
    def _json(data):
        import json
        return json.dumps(data)

    @staticmethod
    def _parse(body):
        import json
        return json.loads(body)


class ReconScanTest(tempest.test.BaseTestCase):
    """Scenario completo: richiesta scansione -> attesa -> risultati."""

    credentials = ["admin"]

    @classmethod
    def skip_checks(cls):
        super().skip_checks()
        if not CONF.recon.enabled:
            raise cls.skipException("I test di Recon-Stack sono disattivati.")

    @classmethod
    def setup_clients(cls):
        super().setup_clients()
        # Client REST verso recon-api, autenticato come admin.
        cls.recon = ReconClient(
            cls.os_admin.auth_provider,
            service="recon",
            region=CONF.identity.region,
            endpoint_type="public")
        cls.projects_client = cls.os_admin.projects_client

    def _demo_project_id(self):
        """Trova l'id del progetto demo dal suo nome (CONF.recon.demo_project)."""
        projects = self.projects_client.list_projects()["projects"]
        for project in projects:
            if project["name"] == CONF.recon.demo_project:
                return project["id"]
        self.skipTest(f"progetto demo '{CONF.recon.demo_project}' non trovato: "
                      f"esegui demo/setup_demo.sh")

    @decorators.idempotent_id("b6e0c0de-0000-4000-8000-000000000011")
    def test_scansione_completa_del_progetto_demo(self):
        project_id = self._demo_project_id()

        # 1. Richiesta di scansione (risponde 202 con lo stato PENDING).
        scan = self.recon.create_scan(project_id)
        scan_id = scan["id"]

        # 2. Attesa che lo scanner la esegua e la porti a DONE (o FAILED).
        def _finita():
            stato = self.recon.get_scan(scan_id)["status"]
            return stato in ("DONE", "FAILED", "REJECTED")

        if not test_utils.call_until_true(_finita, CONF.recon.scan_timeout, 5):
            self.fail("la scansione non si è conclusa entro il tempo massimo")
        self.assertEqual("DONE", self.recon.get_scan(scan_id)["status"])

        # 3. Ci sono host e servizi, e almeno una segnalazione di esposizione
        #    (il demo ha regole volutamente sbagliate: vanno segnalate).
        hosts = self.recon.list_hosts(scan_id)
        self.assertGreaterEqual(len(hosts), 1)
        findings = self.recon.get_exposure(scan_id)
        self.assertGreaterEqual(len(findings), 1)
