# Confronto fra una scansione e la precedente: cosa è comparso e cosa è sparito.
#
# Lo storico sono le scansioni passate di un progetto (tabella scans); il "diff"
# è il confronto fra due di esse (architettura.md). Qui lo calcoliamo fra una
# scansione e quella completata subito prima dello stesso progetto, così si vede
# cosa è cambiato: host comparsi o spariti, host che hanno cambiato
# classificazione, servizi comparsi o spariti.
#
# Gli host si confrontano per indirizzo IP, non per id: l'id di riga cambia a
# ogni scansione, l'indirizzo no. I servizi si confrontano per (porta,
# protocollo, nome) sullo stesso host. Questa è la parte interessante per la
# verifica dello Step 10: avviando o fermando un servizio su una VM, il diff
# mostra la comparsa o la scomparsa.
#
# Le funzioni di confronto (snapshot, diff_snapshots) non toccano il database:
# ricevono liste di oggetti e si provano da sole. diff_for_scan mette insieme le
# due cose leggendo dal database, ed è usata sia dalla API sia dal log a fine
# scansione.

import logging

from recon_stack.db import api as db
from recon_stack.db import models

LOG = logging.getLogger(__name__)


def _service_key(service):
    """Chiave di un servizio per il confronto: porta, protocollo, nome."""
    return (service.port_number, service.protocol, service.name)


def snapshot(hosts, services):
    """Riduce host e servizi di una scansione a una forma comoda al confronto.

    Restituisce un dizionario indicizzato per indirizzo IP:
      { ip: {"classification": ..., "services": { (porta, protocollo, nome) }}}
    I servizi sono un insieme di chiavi: per il diff conta la presenza, non i
    dettagli (prodotto, versione).
    """
    ip_by_host_id = {h.id: h.ip_address for h in hosts}
    snap = {h.ip_address: {"classification": h.classification, "services": set()}
            for h in hosts}
    for service in services:
        ip = ip_by_host_id.get(service.host_id)
        if ip is not None:
            snap[ip]["services"].add(_service_key(service))
    return snap


def _sorted_service_keys(keys):
    # Ordiniamo con il nome eventualmente None trattato come stringa vuota,
    # altrimenti Python non sa confrontare None con una stringa.
    return sorted(keys, key=lambda k: (k[0], k[1], k[2] or ""))


def diff_snapshots(previous, current):
    """Confronta due snapshot e restituisce cosa è comparso e cosa è sparito."""
    prev_ips = set(previous)
    cur_ips = set(current)

    hosts_reclassified = []
    for ip in sorted(prev_ips & cur_ips):
        if previous[ip]["classification"] != current[ip]["classification"]:
            hosts_reclassified.append({
                "ip": ip,
                "from": previous[ip]["classification"],
                "to": current[ip]["classification"],
            })

    def services_delta(source, other):
        # Servizi presenti in `source` ma non in `other`, host per host.
        delta = []
        for ip in sorted(source):
            missing = set(source[ip]["services"])
            missing -= set(other.get(ip, {}).get("services", set()))
            for port, protocol, name in _sorted_service_keys(missing):
                delta.append({"ip": ip, "port": port,
                              "protocol": protocol, "name": name})
        return delta

    return {
        "hosts_appeared": sorted(cur_ips - prev_ips),
        "hosts_disappeared": sorted(prev_ips - cur_ips),
        "hosts_reclassified": hosts_reclassified,
        "services_appeared": services_delta(current, previous),
        "services_disappeared": services_delta(previous, current),
    }


def _scan_snapshot(scan_id):
    """Costruisce lo snapshot di una scansione leggendo dal database."""
    return snapshot(db.get_hosts(scan_id), db.get_services(scan_id=scan_id))


def diff_for_scan(scan_id):
    """Diff di una scansione rispetto alla precedente completata del progetto.

    Restituisce il risultato di diff_snapshots con in più previous_scan_id (o
    None se è la prima scansione del progetto: allora tutto risulta comparso).
    None se la scansione non esiste.
    """
    scan = db.get_scan(scan_id)
    if scan is None:
        return None
    previous = db.get_previous_scan(scan.project_id, scan.created_at,
                                    status=models.SCAN_DONE)
    current_snap = _scan_snapshot(scan_id)
    previous_snap = _scan_snapshot(previous.id) if previous else {}
    result = diff_snapshots(previous_snap, current_snap)
    result["previous_scan_id"] = previous.id if previous else None
    return result


def log_diff(scan_id):
    """Scrive nel log un riepilogo del diff a fine scansione (Step 10).

    Non deve far fallire la scansione: eventuali errori vengono solo registrati.
    """
    try:
        diff = diff_for_scan(scan_id)
        if diff is None:
            return
        LOG.info("diff scansione %s (precedente %s): host +%d/-%d, servizi +%d/-%d, "
                 "riclassificati %d", scan_id, diff["previous_scan_id"],
                 len(diff["hosts_appeared"]), len(diff["hosts_disappeared"]),
                 len(diff["services_appeared"]), len(diff["services_disappeared"]),
                 len(diff["hosts_reclassified"]))
    except Exception:
        LOG.exception("calcolo del diff fallito per la scansione %s", scan_id)
