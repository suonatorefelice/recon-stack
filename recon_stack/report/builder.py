# Raccolta dei dati per il report e redaction (step 12).
#
# gather(scan_id) legge dal database tutto ciò che serve al report e lo riduce a
# un dizionario di tipi semplici (dizionari, liste, stringhe): così la mappa
# (topology.py), l'HTML (render.py) e la redaction lavorano sulla stessa forma,
# senza dipendere dagli oggetti del database.
#
# redact(data) produce una copia "condivisibile" dello stesso dizionario, in cui
# indirizzi IP, nomi delle VM e identificativi reali sono sostituiti da
# pseudonimi coerenti (lo stesso indirizzo diventa sempre lo stesso pseudonimo).
# La sostituzione vale anche dentro il testo delle segnalazioni, non solo nei
# campi: così un IP non resta scritto in chiaro in una frase.

import copy
import json

from recon_stack.db import api as db
from recon_stack.db import models


def gather(scan_id):
    """Raccoglie i dati di una scansione in un dizionario pronto per il report.

    Restituisce None se la scansione non esiste. Gli host portano con sé i propri
    servizi, divisi fra vista interna ed esterna; ci sono poi le segnalazioni di
    esposizione, le subnet del perimetro e i floating IP.
    """
    scan = db.get_scan(scan_id)
    if scan is None:
        return None

    services_by_host = {}
    for svc in db.get_services(scan_id=scan_id):
        services_by_host.setdefault(svc.host_id, []).append(svc)

    hosts = []
    for host in db.get_hosts(scan_id):
        svcs = services_by_host.get(host.id, [])
        hosts.append({
            "ip_address": host.ip_address,
            "classification": host.classification,
            "server_name": host.server_name,
            "network_id": host.network_id,
            "services_internal": _services(svcs, models.VIEW_INTERNAL),
            "services_external": _services(svcs, models.VIEW_EXTERNAL),
        })

    findings = [
        {"type": f.finding_type, "severity": f.severity,
         "ip_address": f.ip_address, "port_number": f.port_number,
         "protocol": f.protocol, "message": f.message}
        for f in db.get_findings(scan_id)
    ]

    inventory = db.get_inventory(scan_id)
    floating_ips = [
        {"floating_ip_address": f.floating_ip_address,
         "fixed_ip_address": f.fixed_ip_address}
        for f in inventory["floating_ips"]
    ]

    # Le subnet del perimetro sono salvate come testo JSON nella scansione.
    subnets = []
    if scan.perimeter:
        subnets = json.loads(scan.perimeter).get("internal_subnets", [])

    return {
        "scan": {
            "id": scan.id,
            "project_id": scan.project_id,
            "status": scan.status,
            "created_at": scan.created_at.isoformat() if scan.created_at else None,
            "finished_at": (scan.finished_at.isoformat()
                            if scan.finished_at else None),
        },
        "subnets": subnets,
        "hosts": hosts,
        "floating_ips": floating_ips,
        "findings": findings,
        "summary": _summary(hosts, findings),
    }


def _services(services, view):
    """I servizi di una vista (interna o esterna), come dizionari ordinati."""
    chosen = [s for s in services if s.view == view]
    chosen.sort(key=lambda s: s.port_number)
    return [
        {"port_number": s.port_number, "protocol": s.protocol, "name": s.name,
         "product": s.product, "version": s.version}
        for s in chosen
    ]


def _summary(hosts, findings):
    """Conteggi per il riepilogo in testa al report."""
    by_class = {models.HOST_KNOWN: 0, models.HOST_UNKNOWN: 0, models.HOST_ABSENT: 0}
    for host in hosts:
        by_class[host["classification"]] = by_class.get(
            host["classification"], 0) + 1
    by_severity = {}
    for finding in findings:
        by_severity[finding["severity"]] = by_severity.get(
            finding["severity"], 0) + 1
    return {
        "hosts_total": len(hosts),
        "hosts_by_classification": by_class,
        "findings_total": len(findings),
        "findings_by_severity": by_severity,
    }


# --- Redaction ---------------------------------------------------------------

class Redactor:
    """Assegna pseudonimi coerenti ai dati sensibili e li applica ai testi.

    Lo stesso valore reale (un IP, un nome di VM, un id di rete) riceve sempre lo
    stesso pseudonimo, una volta sola: così il report resta leggibile (si capisce
    che due righe parlano dello stesso host) senza rivelare i dati veri.
    """

    def __init__(self):
        self._mapping = {}
        self._counters = {}

    def pseudonym(self, value, kind):
        """Pseudonimo per un valore, creandolo la prima volta (None resta None)."""
        if value is None:
            return None
        if value not in self._mapping:
            self._counters[kind] = self._counters.get(kind, 0) + 1
            self._mapping[value] = f"{kind}-{self._counters[kind]}"
        return self._mapping[value]

    def redact_text(self, text):
        """Sostituisce in un testo ogni valore noto con il suo pseudonimo.

        Sostituiamo i valori più lunghi per primi, così un indirizzo non viene
        rovinato da una sostituzione parziale di un pezzo più corto.
        """
        if not text:
            return text
        for real in sorted(self._mapping, key=len, reverse=True):
            text = text.replace(real, self._mapping[real])
        return text


def redact(data):
    """Restituisce una copia del report con i dati sensibili sostituiti.

    Sono sostituiti: indirizzi IP degli host e floating IP, nomi delle VM,
    id di progetto, di rete e di subnet. Nomi dei servizi, porte, prodotti e
    versioni restano: non identificano il cloud.
    """
    data = copy.deepcopy(data)
    r = Redactor()

    # Prima registriamo tutti i valori sensibili, così gli pseudonimi sono
    # assegnati in ordine stabile e le sostituzioni nei testi li conoscono tutti.
    r.pseudonym(data["scan"]["project_id"], "progetto")
    for subnet in data["subnets"]:
        r.pseudonym(subnet.get("network_id"), "rete")
        r.pseudonym(subnet.get("subnet_id"), "subnet")
        r.pseudonym(subnet.get("cidr"), "cidr")
    for host in data["hosts"]:
        r.pseudonym(host["ip_address"], "host")
        r.pseudonym(host["server_name"], "vm")
        r.pseudonym(host["network_id"], "rete")
    for fip in data["floating_ips"]:
        r.pseudonym(fip["floating_ip_address"], "fip")
        r.pseudonym(fip["fixed_ip_address"], "host")

    # Ora applichiamo gli pseudonimi ai campi strutturati e ai testi liberi.
    data["scan"]["project_id"] = r.pseudonym(data["scan"]["project_id"], "progetto")
    for subnet in data["subnets"]:
        subnet["network_id"] = r.pseudonym(subnet.get("network_id"), "rete")
        subnet["subnet_id"] = r.pseudonym(subnet.get("subnet_id"), "subnet")
        subnet["cidr"] = r.pseudonym(subnet.get("cidr"), "cidr")
    for host in data["hosts"]:
        host["ip_address"] = r.pseudonym(host["ip_address"], "host")
        host["server_name"] = r.pseudonym(host["server_name"], "vm")
        host["network_id"] = r.pseudonym(host["network_id"], "rete")
    for fip in data["floating_ips"]:
        fip["floating_ip_address"] = r.pseudonym(fip["floating_ip_address"], "fip")
        fip["fixed_ip_address"] = r.pseudonym(fip["fixed_ip_address"], "host")
    for finding in data["findings"]:
        finding["ip_address"] = r.redact_text(finding["ip_address"])
        finding["message"] = r.redact_text(finding["message"])

    data["redacted"] = True
    return data
