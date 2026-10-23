# Host discovery e classificazione degli host (step 6).
#
# "Host discovery" vuol dire scoprire quali indirizzi del perimetro rispondono.
# La parte che richiede privilegi (entrare nel namespace ed eseguire nmap) è
# isolata in privsep/discovery.py (ADR 0007); qui, senza privilegi, facciamo
# tre cose testabili senza OpenStack:
#   - parse_live_hosts: leggere l'XML prodotto da nmap e ricavarne gli indirizzi
#     che hanno risposto;
#   - classify: confrontare chi ha risposto con l'inventario delle porte Neutron
#     (step 4) e dare a ogni host una classificazione;
#   - discover_network: mettere insieme le due cose per una singola rete.
#
# Classificazione (GLOSSARY.md, models.py):
#   - "censito"     (known):   risponde e ha una porta Neutron -> risorsa nota;
#   - "sconosciuto" (unknown): risponde ma nessuna porta lo spiega -> da indagare;
#   - "assente"     (absent):  ha una porta Neutron ma non risponde.

import logging
from xml.etree import ElementTree

from recon_stack.db import models
from recon_stack.privsep import discovery as priv_discovery
from recon_stack.scanner import namespaces

LOG = logging.getLogger(__name__)

# Le porte dell'infrastruttura di rete (DHCP, router): hanno una porta Neutron
# ma non sono VM. Le riconosciamo dal device_owner per non attribuirle a una VM.
_COMPUTE_OWNER_PREFIX = "compute:"


def parse_live_hosts(nmap_xml):
    """Ricava dall'XML di nmap l'insieme degli indirizzi che hanno risposto.

    nmap elenca un <host> per ogni indirizzo provato, con <status state="up"> se
    ha risposto e un <address> con l'indirizzo. Prendiamo solo quelli "up".
    """
    root = ElementTree.fromstring(nmap_xml)
    live = set()
    for host in root.findall("host"):
        status = host.find("status")
        if status is None or status.get("state") != "up":
            continue
        for address in host.findall("address"):
            if address.get("addrtype") in ("ipv4", "ipv6"):
                live.add(address.get("addr"))
    return live


def classify(network_id, responding_ips, ports, servers_by_id=None):
    """Classifica gli host di una rete confrontando risposte e porte Neutron.

    - network_id: la rete scansionata (per attribuire gli host sconosciuti);
    - responding_ips: insieme di indirizzi che hanno risposto in quella rete;
    - ports: le porte Neutron dell'inventario appartenenti a quella rete
      (oggetti InventoryPort o simili, con ip_address, port_id, ecc.);
    - servers_by_id: mappa id VM -> nome, per dare un nome agli host censiti.

    Restituisce una lista di dizionari, uno per host, con i campi della tabella
    hosts (models.Host).
    """
    servers_by_id = servers_by_id or {}
    ports_by_ip = {p.ip_address: p for p in ports}
    hosts = []

    # 1. Chi ha risposto: censito se ha una porta, altrimenti sconosciuto.
    for ip in sorted(responding_ips):
        port = ports_by_ip.get(ip)
        if port is not None:
            hosts.append(_host_from_port(ip, port, servers_by_id,
                                         models.HOST_KNOWN))
        else:
            hosts.append({
                "ip_address": ip,
                "network_id": network_id,
                "subnet_id": None,
                "neutron_port_id": None,
                "server_id": None,
                "server_name": None,
                "classification": models.HOST_UNKNOWN,
            })

    # 2. Porte che non hanno risposto: host assenti (c'è la porta, non l'host).
    for ip, port in ports_by_ip.items():
        if ip not in responding_ips:
            hosts.append(_host_from_port(ip, port, servers_by_id,
                                         models.HOST_ABSENT))

    return hosts


def _host_from_port(ip, port, servers_by_id, classification):
    """Costruisce il dizionario di un host a partire dalla sua porta Neutron."""
    # Una porta è di una VM se il suo device_owner inizia con "compute:"
    # (es. "compute:nova"); le porte di router e DHCP non lo sono.
    is_vm = (port.device_owner or "").startswith(_COMPUTE_OWNER_PREFIX)
    server_id = port.device_id if is_vm else None
    return {
        "ip_address": ip,
        "network_id": port.network_id,
        "subnet_id": port.subnet_id,
        "neutron_port_id": port.port_id,
        "server_id": server_id,
        "server_name": servers_by_id.get(server_id) if server_id else None,
        "classification": classification,
    }


def discover_network(network_id, targets, ports, servers_by_id=None, driver=None):
    """Esegue l'host discovery su una rete e restituisce gli host classificati.

    Chiama la funzione privilegiata (che entra nel namespace ed esegue nmap),
    analizza il risultato e lo confronta con le porte della rete. I bersagli
    (targets) sono già stati verificati contro il perimetro da chi ci chiama.
    """
    namespace = namespaces.internal_namespace(network_id, driver)
    LOG.info("host discovery nella rete %s (namespace %s): %d indirizzi",
             network_id, namespace, len(targets))
    nmap_xml = priv_discovery.live_hosts_xml(namespace, targets)
    responding = parse_live_hosts(nmap_xml)
    return classify(network_id, responding, ports, servers_by_id)
