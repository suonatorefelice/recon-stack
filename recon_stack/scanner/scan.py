# Esecuzione di una scansione: mette in fila le fasi, nell'ordine di
# vocab.SCAN_PHASES.
#   1. inventario del progetto (VM, porte, floating IP, regole);
#   2. perimetro (ADR 0005), salvato nella scansione;
#   3. per ogni rete: host discovery e service discovery dentro la namespace
#      OVN (ADR 0006, 0007);
#   4. salvataggio di host e servizi (vista interna);
#   5. vista esterna: service discovery sui floating IP;
#   6. esposizione: confronto servizi/security group -> segnalazioni.
# Se una fase fallisce, la scansione è segnata FAILED con il motivo.

import json
import logging

from recon_stack.db import api as db
from recon_stack.db import models
from recon_stack.scanner import discovery
from recon_stack.scanner import exposure
from recon_stack.scanner import inventory
from recon_stack.scanner import perimeter as perimeter_mod
from recon_stack.scanner import services as services_mod

LOG = logging.getLogger(__name__)


def run_scan(conn, scan_id):
    """Esegue la scansione già registrata con questo id e la restituisce.

    conn è la connessione a OpenStack (iniettata, così i test ne usano una finta).
    """
    scan = db.get_scan(scan_id)
    project_id = scan.project_id
    db.update_scan(scan_id, status=models.SCAN_RUNNING,
                   started_at=models.utcnow())
    LOG.info("scansione %s avviata sul progetto %s", scan_id, project_id)

    try:
        # project_id è già un id verificato: lo risolve request_scan (api/v1.py).
        db.update_scan(scan_id, phase=models.PHASE_INVENTORY)
        servers, ports, floating_ips, rules = inventory.collect(
            conn, project_id, scan_id)
        servers_by_id = {s.server_id: s.name for s in servers}

        # Perimetro, scritto subito nel log della scansione (ADR 0005). I floating
        # IP vengono dall'inventario già raccolto: Neutron si legge una volta sola.
        db.update_scan(scan_id, phase=models.PHASE_PERIMETER)
        perimeter = perimeter_mod.build(conn, project_id, floating_ips)
        db.update_scan(scan_id, perimeter=json.dumps(perimeter.as_dict()))

        # Host e service discovery, rete per rete.
        db.update_scan(scan_id, phase=models.PHASE_DISCOVERY)
        all_hosts = []
        # Servizi per (rete, IP): li agganceremo agli host dopo il salvataggio,
        # quando avranno un id. La rete serve perché reti diverse possono avere
        # IP privati uguali.
        services_by_key = {}
        for network_id, targets in perimeter.hosts_by_network().items():
            # I bersagli vengono solo dal perimetro; privsep/discovery.py
            # ricontrolla comunque che siano IP validi.
            net_ports = [p for p in ports if p.network_id == network_id]
            net_hosts = discovery.discover_network(
                network_id, targets, net_ports, servers_by_id)
            all_hosts.extend(net_hosts)

            # Service discovery solo sugli host che rispondono (gli assenti no).
            responding = [h["ip_address"] for h in net_hosts
                          if h["classification"] != models.HOST_ABSENT]
            found = services_mod.discover_services(network_id, responding)
            for ip, svcs in found.items():
                services_by_key[(network_id, ip)] = svcs

        # Salviamo prima gli host (così ottengono un id), poi i loro servizi.
        db.update_scan(scan_id, phase=models.PHASE_SAVING)
        saved_hosts = db.save_hosts(scan_id, all_hosts)
        all_services = []
        for host in saved_hosts:
            svcs = services_by_key.get((host.network_id, host.ip_address))
            for svc in svcs or []:
                all_services.append({
                    **svc,
                    "host_id": host.id,
                    "view": models.VIEW_INTERNAL,
                })
        db.save_services(all_services)

        # Vista esterna: service discovery sui floating IP dalla rete
        # public; i servizi si agganciano all'host del loro IP privato, vista
        # "esterna" (così lo stesso host può avere servizi interni ed esterni).
        db.update_scan(scan_id, phase=models.PHASE_EXTERNAL)
        external_services = _discover_external(
            floating_ips, saved_hosts)
        db.save_services(external_services)

        # Esposizione: confronto servizi/security group -> segnalazioni.
        db.update_scan(scan_id, phase=models.PHASE_EXPOSURE)
        findings = exposure.compute_and_save(scan_id, {
            "ports": ports, "floating_ips": floating_ips,
            "security_group_rules": rules})

        # Completata: azzeriamo la fase.
        db.update_scan(scan_id, status=models.SCAN_DONE,
                       finished_at=models.utcnow(), phase=None)
        LOG.info("scansione %s completata: %d host, %d servizi interni, "
                 "%d esterni, %d segnalazioni", scan_id, len(all_hosts),
                 len(all_services), len(external_services), len(findings))
    except Exception as exc:
        db.update_scan(scan_id, status=models.SCAN_FAILED,
                       finished_at=models.utcnow(), fault=str(exc))
        LOG.exception("scansione %s fallita", scan_id)
        raise

    return db.get_scan(scan_id)


def _discover_external(floating_ips, saved_hosts):
    """Scansiona i floating IP dall'esterno e prepara i servizi da salvare.

    Ritorna dizionari pronti per db.save_services (view=external, host_id dell'IP
    privato). Un floating IP che risponde ma senza host corrispondente va solo
    nel log: non c'è un host a cui legarlo.
    """
    targets = sorted({f.floating_ip_address for f in floating_ips
                      if f.floating_ip_address})
    if not targets:
        return []

    # Lo stesso IP privato può esistere su più reti: il floating IP punta a una
    # porta Neutron precisa, quindi si cerca prima per porta, poi per IP.
    hosts_by_port = {h.neutron_port_id: h for h in saved_hosts
                     if h.neutron_port_id}
    hosts_by_ip = {h.ip_address: h for h in saved_hosts}
    found = services_mod.discover_external_services(targets)

    external_services = []
    for fip in floating_ips:
        svcs = found.get(fip.floating_ip_address)
        if not svcs:
            continue
        host = (hosts_by_port.get(fip.port_id)
                or hosts_by_ip.get(fip.fixed_ip_address))
        if host is None:
            LOG.warning("il floating IP %s risponde ma il suo IP privato %s non "
                        "è fra gli host della scansione: servizi esterni non "
                        "salvati", fip.floating_ip_address, fip.fixed_ip_address)
            continue
        for svc in svcs:
            external_services.append({
                **svc,
                "host_id": host.id,
                "view": models.VIEW_EXTERNAL,
            })
    return external_services
