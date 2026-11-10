# Confronto fra una scansione e la precedente completata dello stesso progetto:
# host comparsi, spariti o riclassificati e servizi comparsi o spariti.
# Gli host si confrontano per (rete, IP): l'id di riga cambia a ogni scansione
# e l'IP da solo non basta, perché due reti possono riusarlo. I servizi si
# confrontano per (porta, protocollo, nome) sullo stesso host.
# snapshot e diff_snapshots lavorano su dati in memoria; diff_for_scan li
# legge dal database.

from recon_stack.db import api as db
from recon_stack.db import models


def _service_key(service):
    """Chiave di un servizio per il confronto: porta, protocollo, nome."""
    return (service.port_number, service.protocol, service.name)


def _host_key(host):
    """Identità di un host: (rete, IP). Due reti possono riusare gli stessi IP."""
    return (host.network_id, host.ip_address)


def snapshot(hosts, services):
    """Riduce host e servizi a una forma comoda al confronto, indicizzata per
    (rete, IP): { (network_id, ip): {"ip": ..., "classification": ...,
    "services": {(porta, protocollo, nome)}} }. "ip" resta leggibile per i messaggi."""
    key_by_host_id = {h.id: _host_key(h) for h in hosts}
    snap = {_host_key(h): {"ip": h.ip_address,
                           "classification": h.classification, "services": set()}
            for h in hosts}
    for service in services:
        key = key_by_host_id.get(service.host_id)
        if key is not None:
            snap[key]["services"].add(_service_key(service))
    return snap


def _sorted_keys(keys):
    # network_id può essere None (Python non confronta None con str).
    return sorted(keys, key=lambda k: (k[1], k[0] or ""))


def _sorted_service_keys(keys):
    # Nome None trattato come stringa vuota (Python non confronta None con str).
    return sorted(keys, key=lambda k: (k[0], k[1], k[2] or ""))


def diff_snapshots(previous, current):
    """Confronta due snapshot: cosa è comparso e cosa è sparito."""
    prev_keys = set(previous)
    cur_keys = set(current)

    def services_delta(source, other):
        # Servizi presenti in `source` ma non in `other`, host per host.
        delta = []
        for key in _sorted_keys(source):
            missing = set(source[key]["services"])
            missing -= set(other.get(key, {}).get("services", set()))
            for port, protocol, name in _sorted_service_keys(missing):
                delta.append({"ip": source[key]["ip"], "port": port,
                              "protocol": protocol, "name": name})
        return delta

    return {
        "hosts_appeared": [current[k]["ip"]
                           for k in _sorted_keys(cur_keys - prev_keys)],
        "hosts_disappeared": [previous[k]["ip"]
                              for k in _sorted_keys(prev_keys - cur_keys)],
        "services_appeared": services_delta(current, previous),
        "services_disappeared": services_delta(previous, current),
    }


def _scan_snapshot(scan_id):
    """Snapshot di una scansione letto dal database."""
    return snapshot(db.get_hosts(scan_id), db.get_services(scan_id=scan_id))


def diff_for_scan(scan_id):
    """Diff di una scansione rispetto alla precedente completata del progetto.

    Aggiunge previous_scan_id (None se è la prima: allora tutto risulta comparso).
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
