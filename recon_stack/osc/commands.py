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

import ipaddress
import sys
import time

from cliff import lister
from cliff import show
from osc_lib import exceptions

from recon_stack.db import models


def _client(command):
    """Il ReconClient esposto dal plugin (osc/plugin.py)."""
    return command.app.client_manager.recon


def _project_id(command, name_or_id):
    """Id del progetto indicato con --project, che può essere un nome o un id.

    La API lavora con gli id dei progetti; chi usa la riga di comando scrive di
    solito il nome (es. recon-demo). Come gli altri comandi "openstack", lo
    risolviamo con Keystone tramite la connessione openstacksdk che la CLI
    mette a disposizione dei plugin (client_manager.sdk_connection).
    Prima di questa funzione il nome arrivava tale e quale alla API, che non
    trovava niente: "host list --project recon-demo" era vuoto (trovato nel
    test su DevStack).
    """
    if name_or_id is None:
        return None
    identity = command.app.client_manager.sdk_connection.identity
    project = identity.find_project(name_or_id, ignore_missing=True)
    if project is None:
        raise exceptions.CommandError(f"progetto '{name_or_id}' non trovato")
    return project.id


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
            project_id=_project_id(self, parsed_args.project), scan_id=parsed_args.scan,
            classification=parsed_args.classification)
        rows = [tuple(h.get(c) for c in self.columns) for h in hosts]
        return self.headers, rows


class ShowHost(show.ShowOne):
    """Mostra un host e i servizi trovati su di esso."""

    def get_parser(self, prog_name):
        parser = super().get_parser(prog_name)
        parser.add_argument("host", metavar="<host>",
                            help="Id dell'host, oppure il suo indirizzo IP "
                                 "(es. 10.10.10.142).")
        # Servono solo quando si indica un IP: restringono il catalogo in cui
        # cercare l'indirizzo (utile se lo stesso IP compare in più scansioni).
        parser.add_argument("--project", metavar="<progetto>",
                            help="Se indichi un IP, cercalo nel catalogo di "
                                 "questo progetto.")
        parser.add_argument("--scan", metavar="<id-scansione>",
                            help="Se indichi un IP, cercalo in questa scansione.")
        return parser

    def take_action(self, parsed_args):
        client = _client(self)
        host_ref = parsed_args.host
        # Chi fa la demo ragiona per indirizzi, non per UUID: se l'argomento è
        # un IP lo risolviamo all'id dell'host nel catalogo, poi proseguiamo.
        if _looks_like_ip(host_ref):
            host_ref = _resolve_host_by_ip(
                client, host_ref,
                project_id=_project_id(self, getattr(parsed_args, "project", None)),
                scan_id=getattr(parsed_args, "scan", None))
        host = client.get_host(host_ref)
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
            project_id=_project_id(self, parsed_args.project), scan_id=parsed_args.scan,
            name=parsed_args.name)
        # "Vista" distingue lo stesso servizio visto dall'interno della rete e
        # dall'esterno sul floating IP: senza, le due righe sembrano doppioni.
        headers = ("Indirizzo IP", "Porta", "Protocollo", "Servizio", "Prodotto",
                   "Versione", "Vista")
        keys = ("ip_address", "port_number", "protocol", "name", "product",
                "version", "view")
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
            project_id=_project_id(self, parsed_args.project), status=parsed_args.status)
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
        client = _client(self)
        scan = client.get_scan(parsed_args.scan)
        # Riepilogo delle segnalazioni di esposizione: così dal solo "show" vedi
        # la salute della scansione, senza lanciare anche "exposure".
        return _scan_show(scan, _safe_exposure(client, scan))


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
                            help="Nome o id del progetto da scansionare.")
        parser.add_argument("--wait", action="store_true",
                            help="Aspetta che la scansione finisca e mostra "
                                 "l'esito, invece di tornare subito.")
        parser.add_argument("--timeout", metavar="<secondi>", type=int,
                            default=180,
                            help="Con --wait, quanto aspettare al massimo "
                                 "(default 180).")
        parser.add_argument("--interval", metavar="<secondi>", type=int,
                            default=3,
                            help="Con --wait, ogni quanto ricontrollare "
                                 "(default 3).")
        return parser

    def take_action(self, parsed_args):
        client = _client(self)
        scan = client.create_scan(_project_id(self, parsed_args.project))
        if not getattr(parsed_args, "wait", False):
            return _scan_show(scan)
        # Con --wait seguiamo la scansione fino alla fine. L'avanzamento va su
        # stderr, così lo stdout resta la sola tabella finale (comodo per gli
        # script e per i formati -f json/-f value).
        def _progress(s):
            fase = s.get("phase") or s.get("status")
            print(f"… scansione in corso (fase: {fase})", file=sys.stderr)

        scan = _wait_for_scan(
            client, scan["id"],
            timeout=getattr(parsed_args, "timeout", 180),
            interval=getattr(parsed_args, "interval", 3),
            progress=_progress)
        return _scan_show(scan, _safe_exposure(client, scan))


# --- Host per indirizzo IP ---------------------------------------------------

def _looks_like_ip(value):
    """True se la stringa è un indirizzo IP (v4 o v6), non un UUID."""
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _resolve_host_by_ip(client, ip, project_id=None, scan_id=None):
    """Trova l'id dell'host che ha quell'indirizzo nel catalogo.

    Cerca fra gli host (dell'ultima scansione completata, o del progetto/scansione
    indicati) quello con l'IP dato. Se non c'è, errore chiaro.
    """
    for host in client.list_hosts(project_id=project_id, scan_id=scan_id):
        if host.get("ip_address") == ip:
            return host["id"]
    dove = " del progetto" if project_id else (" di quella scansione" if scan_id
                                               else " dell'ultima scansione")
    raise exceptions.CommandError(
        f"nessun host con indirizzo {ip} nel catalogo{dove}")


# --- Attesa della fine di una scansione (--wait) -----------------------------

# Stati in cui una scansione è finita: non cambieranno più.
_FINAL_STATES = (models.SCAN_DONE, models.SCAN_FAILED, models.SCAN_REJECTED)


def _wait_for_scan(client, scan_id, timeout, interval,
                   sleep=time.sleep, monotonic=time.monotonic, progress=None):
    """Interroga la scansione finché non finisce o scade il tempo.

    Ritorna la scansione finale (DONE/FAILED/REJECTED). Se non finisce entro
    `timeout` secondi, alza un errore che ricorda come ricontrollarla dopo.
    sleep/monotonic sono iniettabili per i test (niente attese vere).
    """
    deadline = monotonic() + timeout
    scan = client.get_scan(scan_id)
    while scan.get("status") not in _FINAL_STATES:
        if monotonic() >= deadline:
            raise exceptions.CommandError(
                f"la scansione {scan_id} non è finita entro {timeout}s; "
                f"ricontrolla con 'openstack recon scan show {scan_id}'")
        if progress:
            progress(scan)
        sleep(interval)
        scan = client.get_scan(scan_id)
    return scan


# --- Riepilogo delle segnalazioni --------------------------------------------

# Gravità -> parola per il riepilogo (una mappa piccola e locale: la CLI non
# dipende dalla dashboard). Le gravità sono quelle di scanner/exposure.
_SEVERITY_WORD = {"high": "Grave", "medium": "Media", "low": "Bassa",
                  "info": "Info"}
_SEVERITY_ORDER = ("high", "medium", "low", "info")


def _safe_exposure(client, scan):
    """Le segnalazioni di una scansione, ma solo se è conclusa (DONE).

    Per una scansione non ancora conclusa non ci sono segnalazioni da riassumere;
    torniamo None. Se la chiamata fallisce non blocchiamo il comando.
    """
    if scan.get("status") != models.SCAN_DONE:
        return None
    try:
        return client.get_scan_exposure(scan["id"])
    except Exception:
        return None


def _exposure_summary(findings):
    """Riga di riepilogo, es. 'Grave: 3 · Media: 1 · Bassa: 2 · Info: 1'.

    None (scansione non conclusa) -> '—'; nessuna segnalazione -> 'nessuna'.
    """
    if findings is None:
        return "—"
    if not findings:
        return "nessuna"
    conteggi = {}
    for f in findings:
        sev = f.get("severity")
        conteggi[sev] = conteggi.get(sev, 0) + 1
    pezzi = [f"{_SEVERITY_WORD[s]}: {conteggi[s]}"
             for s in _SEVERITY_ORDER if conteggi.get(s)]
    # Eventuali gravità non previste finiscono comunque in coda, senza perderle.
    pezzi += [f"{s}: {n}" for s, n in conteggi.items()
              if s not in _SEVERITY_WORD]
    return " · ".join(pezzi)


# --- Formattazione condivisa -------------------------------------------------

def _format_service(service):
    """Un servizio in una riga, es. '22/tcp ssh OpenSSH 8.9p1 (vista esterna)'."""
    pezzi = (service.get("name"), service.get("product"), service.get("version"))
    descr = " ".join(p for p in pezzi if p)
    line = f"{service.get('port_number')}/{service.get('protocol')} {descr}".rstrip()
    if service.get("view") == "external":
        line += " (vista esterna)"
    return line


def _format_diff_service(service):
    """Un servizio del diff in una riga, es. '10.0.0.5 22/tcp ssh'."""
    name = service.get("name") or ""
    return f"{service['ip']} {service['port']}/{service['protocol']} {name}".rstrip()


def _scan_show(scan, findings=None):
    """Colonne e valori per mostrare una scansione (usato da show e start).

    `findings` sono le segnalazioni di esposizione, se disponibili: aggiungono la
    riga di riepilogo "Segnalazioni". None = scansione non conclusa (mostra "—").
    """
    columns = ("ID", "Progetto", "Stato", "Fase", "Origine", "Richiesta da",
               "Creata", "Avviata", "Conclusa", "Motivo", "Segnalazioni")
    values = (scan.get("id"), scan.get("project_id"), scan.get("status"),
              scan.get("phase"),
              scan.get("trigger"), scan.get("requested_by_user"),
              scan.get("created_at"), scan.get("started_at"),
              scan.get("finished_at"), scan.get("fault"),
              _exposure_summary(findings))
    return columns, values
