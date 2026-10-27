# Esecuzione di una scansione (step 6 e 7).
#
# Mette in fila i pezzi costruiti negli step precedenti e li fa diventare una
# scansione vera:
#   1. segna la scansione "in corso";
#   2. calcola il perimetro leggendo Neutron (ADR 0005) e lo scrive nel log;
#   3. raccoglie l'inventario del progetto (step 4);
#   4. per ogni rete del perimetro entra nella sua namespace (ADR 0006, 0007),
#      scopre gli host che rispondono e li classifica confrontandoli con le
#      porte Neutron (step 6); sugli host che hanno risposto (censiti e
#      sconosciuti) cerca i servizi in ascolto (step 7);
#   5. salva host e servizi e segna la scansione "completata".
#
# Se qualcosa va storto (Neutron irraggiungibile, perimetro troppo grande, un
# bersaglio fuori perimetro) la scansione viene segnata "fallita" con il motivo,
# invece di proseguire: così il log dice sempre cosa è successo.

import json
import logging

from recon_stack.db import api as db
from recon_stack.db import models
from recon_stack.scanner import diff as diff_mod
from recon_stack.scanner import discovery
from recon_stack.scanner import inventory
from recon_stack.scanner import perimeter as perimeter_mod
from recon_stack.scanner import services as services_mod

LOG = logging.getLogger(__name__)


def run_scan(conn, scan_id):
    """Esegue la scansione già registrata con questo id e la restituisce.

    conn è la connessione a OpenStack (scanner/cloud.py), passata dall'esterno
    così i test possono usarne una finta.
    """
    scan = db.get_scan(scan_id)
    project_id = scan.project_id
    db.update_scan(scan_id, status=models.SCAN_RUNNING,
                   started_at=models.utcnow())
    LOG.info("scansione %s avviata sul progetto %s", scan_id, project_id)

    try:
        # 2. Perimetro, scritto subito nel log della scansione (ADR 0005).
        perimeter = perimeter_mod.build(conn, project_id)
        db.update_scan(scan_id, perimeter=json.dumps(perimeter.as_dict()))

        # 3. Inventario del progetto (VM, porte, floating IP, security group).
        servers, ports, _floating, _sgs, _rules = inventory.collect_and_save(
            conn, project_id, scan_id)
        servers_by_id = {s.server_id: s.name for s in servers}

        # 4. Host discovery e service discovery, rete per rete.
        all_hosts = []
        # Servizi trovati, indicizzati per (rete, IP): li agganceremo agli host
        # dopo averli salvati, quando ogni host avrà il suo id. Usiamo la rete
        # oltre all'IP perché reti diverse possono avere IP privati uguali.
        services_by_key = {}
        for network_id, targets in perimeter.hosts_by_network().items():
            # Controllo del perimetro appena prima di scansionare: è il punto
            # unico che garantisce di non toccare indirizzi fuori perimetro.
            perimeter.check(targets)
            net_ports = [p for p in ports if p.network_id == network_id]
            net_hosts = discovery.discover_network(
                network_id, targets, net_ports, servers_by_id)
            all_hosts.extend(net_hosts)

            # Service discovery solo sugli host che hanno risposto (censiti e
            # sconosciuti): gli assenti non rispondono, inutile interrogarli.
            responding = [h["ip_address"] for h in net_hosts
                          if h["classification"] != models.HOST_ABSENT]
            found = services_mod.discover_services(network_id, responding)
            for ip, svcs in found.items():
                services_by_key[(network_id, ip)] = svcs

        # 5. Salvataggio e chiusura. Salviamo prima gli host (così ottengono un
        # id), poi i servizi collegati al rispettivo host.
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

        db.update_scan(scan_id, status=models.SCAN_DONE,
                       finished_at=models.utcnow())
        LOG.info("scansione %s completata: %d host, %d servizi",
                 scan_id, len(all_hosts), len(all_services))

        # Confronto con la scansione precedente: comparse e scomparse (Step 10).
        # Solo un riepilogo nel log; non deve far fallire la scansione.
        diff_mod.log_diff(scan_id)
    except Exception as exc:
        db.update_scan(scan_id, status=models.SCAN_FAILED,
                       finished_at=models.utcnow(), fault=str(exc))
        LOG.exception("scansione %s fallita", scan_id)
        raise

    return db.get_scan(scan_id)
