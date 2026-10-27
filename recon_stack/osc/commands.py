# I comandi "openstack recon ..." (Step 8).
#
# Ogni classe è un comando dell'OpenStackClient, costruito su cliff (la libreria
# dei comandi usata da `openstack`). L'entry point in setup.cfg lega il nome del
# comando alla classe: ad esempio "recon_host_list" -> `openstack recon host list`.
#
# I comandi fanno una cosa sola: leggere le opzioni, chiamare il client HTTP
# (osc/client.py, raggiungibile come self.app.client_manager.recon) e presentare
# il risultato. cliff si occupa di stamparlo nel formato scelto dall'utente
# (tabella, JSON, CSV, ...): un comando "lista" restituisce (colonne, righe), un
# comando "mostra" restituisce (colonne, valori).

from cliff import lister
from cliff import show


def _client(command):
    """Il ReconClient esposto dal plugin (osc/plugin.py)."""
    return command.app.client_manager.recon


# --- Host --------------------------------------------------------------------

class ListHost(lister.Lister):
    """Elenca gli host del catalogo (ultima scansione completata)."""

    columns = ("id", "ip_address", "classification", "server_name", "network_id")
    headers = ("ID", "Indirizzo IP", "Classificazione", "VM", "Rete")

    def get_parser(self, prog_name):
        parser = super().get_parser(prog_name)
        parser.add_argument("--project", metavar="<progetto>",
                            help="Mostra il catalogo di questo progetto.")
        parser.add_argument("--scan", metavar="<id-scansione>",
                            help="Mostra gli host di una scansione precisa.")
        parser.add_argument("--classification", metavar="<classe>",
                            choices=("known", "unknown", "absent"),
                            help="Filtra per classificazione dell'host.")
        return parser

    def take_action(self, parsed_args):
        hosts = _client(self).list_hosts(
            project_id=parsed_args.project, scan_id=parsed_args.scan,
            classification=parsed_args.classification)
        rows = [tuple(h.get(c) for c in self.columns) for h in hosts]
        return self.headers, rows


class ShowHost(show.ShowOne):
    """Mostra un host e i servizi trovati su di esso."""

    def get_parser(self, prog_name):
        parser = super().get_parser(prog_name)
        parser.add_argument("host", metavar="<id-host>",
                            help="Id dell'host da mostrare.")
        return parser

    def take_action(self, parsed_args):
        host = _client(self).get_host(parsed_args.host)
        # I servizi li mostriamo come testo riassuntivo, uno per riga, così
        # stanno in un solo campo della vista "mostra".
        services = "\n".join(
            _format_service(s) for s in host.get("services", [])) or "-"
        columns = ("ID", "Indirizzo IP", "Classificazione", "VM", "Rete",
                   "Porta Neutron", "Servizi")
        values = (host.get("id"), host.get("ip_address"),
                  host.get("classification"), host.get("server_name"),
                  host.get("network_id"), host.get("neutron_port_id"), services)
        return columns, values


# --- Servizi -----------------------------------------------------------------

class ListService(lister.Lister):
    """Elenca i servizi del catalogo, con ricerca per nome."""

    def get_parser(self, prog_name):
        parser = super().get_parser(prog_name)
        parser.add_argument("--project", metavar="<progetto>",
                            help="Cerca nel catalogo di questo progetto.")
        parser.add_argument("--scan", metavar="<id-scansione>",
                            help="Cerca in una scansione precisa.")
        parser.add_argument("--name", metavar="<nome>",
                            help="Filtra per nome del servizio (es. ssh).")
        return parser

    def take_action(self, parsed_args):
        services = _client(self).list_services(
            project_id=parsed_args.project, scan_id=parsed_args.scan,
            name=parsed_args.name)
        headers = ("Host", "Porta", "Protocollo", "Servizio", "Prodotto", "Versione")
        keys = ("host_id", "port_number", "protocol", "name", "product", "version")
        rows = [tuple(s.get(k) for k in keys) for s in services]
        return headers, rows


# --- Scansioni ---------------------------------------------------------------

class ListScan(lister.Lister):
    """Elenca le scansioni, dalla più recente."""

    columns = ("id", "project_id", "status", "trigger", "created_at")
    headers = ("ID", "Progetto", "Stato", "Origine", "Creata")

    def get_parser(self, prog_name):
        parser = super().get_parser(prog_name)
        parser.add_argument("--project", metavar="<progetto>",
                            help="Filtra per progetto.")
        parser.add_argument("--status", metavar="<stato>",
                            help="Filtra per stato (PENDING, DONE, FAILED, ...).")
        return parser

    def take_action(self, parsed_args):
        scans = _client(self).list_scans(
            project_id=parsed_args.project, status=parsed_args.status)
        rows = [tuple(s.get(c) for c in self.columns) for s in scans]
        return self.headers, rows


class ShowScan(show.ShowOne):
    """Mostra il dettaglio di una scansione."""

    def get_parser(self, prog_name):
        parser = super().get_parser(prog_name)
        parser.add_argument("scan", metavar="<id-scansione>",
                            help="Id della scansione da mostrare.")
        return parser

    def take_action(self, parsed_args):
        return _scan_show(_client(self).get_scan(parsed_args.scan))


class DiffScan(show.ShowOne):
    """Mostra cosa è cambiato fra una scansione e la precedente completata."""

    def get_parser(self, prog_name):
        parser = super().get_parser(prog_name)
        parser.add_argument("scan", metavar="<id-scansione>",
                            help="Id della scansione da confrontare.")
        return parser

    def take_action(self, parsed_args):
        diff = _client(self).get_scan_diff(parsed_args.scan)
        columns = ("Scansione precedente", "Host comparsi", "Host spariti",
                   "Host riclassificati", "Servizi comparsi", "Servizi spariti")
        values = (
            diff.get("previous_scan_id") or "-",
            "\n".join(diff["hosts_appeared"]) or "-",
            "\n".join(diff["hosts_disappeared"]) or "-",
            "\n".join(f"{h['ip']}: {h['from']} -> {h['to']}"
                      for h in diff["hosts_reclassified"]) or "-",
            "\n".join(_format_diff_service(s) for s in diff["services_appeared"]) or "-",
            "\n".join(_format_diff_service(s) for s in diff["services_disappeared"]) or "-",
        )
        return columns, values


class ExposureScan(lister.Lister):
    """Elenca le segnalazioni di esposizione di una scansione (step 11)."""

    def get_parser(self, prog_name):
        parser = super().get_parser(prog_name)
        parser.add_argument("scan", metavar="<id-scansione>",
                            help="Id della scansione di cui mostrare le segnalazioni.")
        parser.add_argument("--severity", metavar="<gravità>",
                            choices=("high", "medium", "low", "info"),
                            help="Filtra per gravità (high, medium, low, info).")
        return parser

    def take_action(self, parsed_args):
        findings = _client(self).get_scan_exposure(
            parsed_args.scan, severity=parsed_args.severity)
        headers = ("Gravità", "Tipo", "Indirizzo", "Porta", "Descrizione")
        rows = [(f.get("severity"), f.get("type"), f.get("ip_address"),
                 f.get("port_number"), f.get("message")) for f in findings]
        return headers, rows


class StartScan(show.ShowOne):
    """Avvia una nuova scansione di un progetto (serve il ruolo admin)."""

    def get_parser(self, prog_name):
        parser = super().get_parser(prog_name)
        parser.add_argument("--project", metavar="<progetto>", required=True,
                            help="Id del progetto da scansionare.")
        return parser

    def take_action(self, parsed_args):
        return _scan_show(_client(self).create_scan(parsed_args.project))


# --- Formattazione condivisa -------------------------------------------------

def _format_service(service):
    """Un servizio in una riga, es. '22/tcp ssh OpenSSH 8.9p1'."""
    pezzi = (service.get("name"), service.get("product"), service.get("version"))
    descr = " ".join(p for p in pezzi if p)
    return f"{service.get('port_number')}/{service.get('protocol')} {descr}".rstrip()


def _format_diff_service(service):
    """Un servizio del diff in una riga, es. '10.0.0.5 22/tcp ssh'."""
    name = service.get("name") or ""
    return f"{service['ip']} {service['port']}/{service['protocol']} {name}".rstrip()


def _scan_show(scan):
    """Colonne e valori per mostrare una scansione (usato da show e start)."""
    columns = ("ID", "Progetto", "Stato", "Origine", "Richiesta da",
               "Creata", "Avviata", "Conclusa", "Motivo")
    values = (scan.get("id"), scan.get("project_id"), scan.get("status"),
              scan.get("trigger"), scan.get("requested_by_user"),
              scan.get("created_at"), scan.get("started_at"),
              scan.get("finished_at"), scan.get("fault"))
    return columns, values
