# Host discovery e classificazione: scopre quali indirizzi del perimetro
# rispondono. La parte privilegiata (namespace + nmap) è in privsep/discovery.py
# (ADR 0007); qui, senza privilegi: parse_live_hosts (legge l'XML di nmap),
# classify (confronta chi risponde con le porte Neutron) e discover_network (le
# mette insieme per una rete). Classificazione (GLOSSARY.md):
#   known   = risponde e ha una porta Neutron;
#   unknown = risponde ma nessuna porta lo spiega (da indagare);
#   absent  = ha una porta Neutron ma non risponde.

import logging
from xml.etree import ElementTree

from recon_stack import vocab
from recon_stack.db import models
from recon_stack.privsep import discovery as priv_discovery

LOG = logging.getLogger(__name__)


def internal_namespace(network_id):
    """Nome della namespace di metadati OVN collegata alla rete: 'ovnmeta-<id rete>'.

    Il nodo non ha un'interfaccia diretta sulle reti private, ma Neutron (con
    OVN) crea sul nodo delle namespace di metadati collegate ad esse: si esegue
    il comando lì dentro (ip netns exec <namespace> ...), ADR 0006.
    """
    return f"ovnmeta-{network_id}"


def parse_live_hosts(nmap_xml):
    """Dall'XML di nmap ricava l'insieme degli indirizzi che hanno risposto (status up)."""
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

    ports sono le porte Neutron della rete; servers_by_id mappa id VM -> nome.
    Ritorna una lista di dizionari coi campi di models.Host.
    """
    servers_by_id = servers_by_id or {}
    ports_by_ip = {p.ip_address: p for p in ports}
    hosts = []

    # Chi ha risposto: censito se ha una porta, altrimenti sconosciuto.
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

    # Porte che non hanno risposto: host assenti (c'è la porta, non l'host).
    for ip, port in ports_by_ip.items():
        if ip not in responding_ips:
            hosts.append(_host_from_port(ip, port, servers_by_id,
                                         models.HOST_ABSENT))

    return hosts


def _host_from_port(ip, port, servers_by_id, classification):
    """Dizionario di un host a partire dalla sua porta Neutron."""
    # È di una VM se device_owner inizia con "compute:" (non router o metadati).
    is_vm = (port.device_owner or "").startswith(vocab.COMPUTE_OWNER_PREFIX)
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


def discover_network(network_id, targets, ports, servers_by_id=None):
    """Host discovery su una rete; ritorna gli host classificati.

    Ogni target viene validato come IP valido nel confine privsep, prima di
    costruire il comando nmap (vedi privsep/discovery.py).
    """
    namespace = internal_namespace(network_id)
    LOG.info("host discovery nella rete %s (namespace %s): %d indirizzi",
             network_id, namespace, len(targets))
    nmap_xml = priv_discovery.live_hosts_xml(namespace, targets)
    responding = parse_live_hosts(nmap_xml)
    return classify(network_id, responding, ports, servers_by_id)
