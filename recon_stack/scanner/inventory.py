# Raccolta dell'inventario da Nova e Neutron (step 4).
#
# All'inizio di ogni scansione il servizio legge da OpenStack quali risorse ci
# sono nel progetto da scansionare:
#   - le VM (server Nova);
#   - le porte Neutron, cioè le "prese di rete" virtuali a cui sono attaccati
#     gli IP dei progetti (una VM ha di solito una porta per rete);
#   - i floating IP, gli indirizzi pubblici che inoltrano verso un IP privato.
#
# Questa fotografia serve a due cose: calcolare il perimetro (step 5) e, dopo la
# scansione, capire se un IP che risponde appartiene a una porta nota (host
# "censito") o no (host "sconosciuto", step 6).
#
# Il servizio legge soltanto (ADR 0003): qui non si crea né si modifica nulla.
# Le funzioni ricevono la connessione (conn) dall'esterno invece di aprirla:
# così i test passano una connessione finta e non serve un OpenStack vero.

import logging

from recon_stack.db import api
from recon_stack.db import models

LOG = logging.getLogger(__name__)


def collect(conn, project_id, scan_id):
    """Legge l'inventario del progetto e lo trasforma in righe da salvare.

    Restituisce tre liste di oggetti (server, porte, floating IP) già legati
    alla scansione scan_id, ma non ancora salvati: le salva collect_and_save.
    Usiamo project_id per chiedere a OpenStack solo le risorse di quel progetto.
    """
    servers = [
        models.InventoryServer(
            scan_id=scan_id,
            server_id=server.id,
            name=server.name,
            status=server.status,
        )
        # all_projects=True perché il servizio gira come admin e di default
        # vedrebbe solo il proprio progetto; project_id filtra su quello voluto.
        for server in conn.compute.servers(all_projects=True, project_id=project_id)
    ]

    ports = []
    for port in conn.network.ports(project_id=project_id):
        # Una porta può avere più IP fissi: salviamo una riga per ciascuno, così
        # ogni riga ha un solo indirizzo (vedi InventoryPort in models.py).
        for fixed in port.fixed_ips or []:
            ports.append(models.InventoryPort(
                scan_id=scan_id,
                port_id=port.id,
                network_id=port.network_id,
                subnet_id=fixed.get("subnet_id"),
                ip_address=fixed.get("ip_address"),
                mac_address=port.mac_address,
                device_owner=port.device_owner,
                device_id=port.device_id,
            ))

    floating_ips = [
        models.InventoryFloatingIp(
            scan_id=scan_id,
            floating_ip_id=fip.id,
            floating_ip_address=fip.floating_ip_address,
            fixed_ip_address=fip.fixed_ip_address,
            port_id=fip.port_id,
        )
        for fip in conn.network.ips(project_id=project_id)
    ]

    LOG.info("inventario del progetto %s: %d VM, %d IP di porta, %d floating IP",
             project_id, len(servers), len(ports), len(floating_ips))
    return servers, ports, floating_ips


def collect_and_save(conn, project_id, scan_id):
    """Legge l'inventario del progetto e lo salva nel database.

    È la funzione che userà la scansione vera; restituisce le tre liste salvate.
    """
    servers, ports, floating_ips = collect(conn, project_id, scan_id)
    api.save_inventory(servers, ports, floating_ips)
    return servers, ports, floating_ips
