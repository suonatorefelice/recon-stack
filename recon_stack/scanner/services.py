# Service discovery: dopo l'host discovery (quali IP rispondono), scopre
# COSA gira su quegli IP — per ogni porta aperta il servizio, il prodotto e la
# versione, con nmap -sV. La parte privilegiata (entrare nel namespace, eseguire
# nmap) è in privsep/discovery.py (ADR 0007); qui, senza privilegi, leggiamo
# l'XML di nmap (parse_services) e lanciamo la scansione (discover_services).

import logging
from xml.etree import ElementTree

from recon_stack import conf
from recon_stack.privsep import discovery as priv_discovery
from recon_stack.scanner import discovery

LOG = logging.getLogger(__name__)


def parse_services(nmap_xml):
    """Dall'XML di nmap ricava i servizi sulle porte aperte, per indirizzo IP.

    Ritorna {ip: [{port_number, protocol, name, product, version}, ...]}. Gli
    attributi che nmap non riconosce restano None; gli IP senza porte aperte non
    compaiono.
    """
    root = ElementTree.fromstring(nmap_xml)
    result = {}
    for host in root.findall("host"):
        ip = _host_address(host)
        if ip is None:
            continue
        services = []
        ports = host.find("ports")
        if ports is not None:
            for port in ports.findall("port"):
                state = port.find("state")
                # Solo le porte davvero aperte (non "closed"/"filtered").
                if state is None or state.get("state") != "open":
                    continue
                service = port.find("service")
                services.append({
                    "port_number": int(port.get("portid")),
                    "protocol": port.get("protocol"),
                    "name": service.get("name") if service is not None else None,
                    "product": service.get("product") if service is not None else None,
                    "version": service.get("version") if service is not None else None,
                })
        if services:
            result[ip] = services
    return result


def _host_address(host):
    """L'indirizzo IPv4 o IPv6 di un elemento <host>, oppure None."""
    for address in host.findall("address"):
        if address.get("addrtype") in ("ipv4", "ipv6"):
            return address.get("addr")
    return None


def discover_services(network_id, targets):
    """Service discovery su una rete; ritorna i servizi per IP.

    targets sono gli host che hanno risposto (già nel perimetro). Senza bersagli
    non entra nel namespace. La profondità viene da [scanner] service_scan_scope.
    """
    if not targets:
        return {}
    namespace = discovery.internal_namespace(network_id)
    scope = conf.CONF.scanner.service_scan_scope
    LOG.info("service discovery nella rete %s (namespace %s): %d host, "
             "profondità '%s'", network_id, namespace, len(targets), scope)
    nmap_xml = priv_discovery.service_scan_xml(namespace, list(targets), scope)
    return parse_services(nmap_xml)


def discover_external_services(targets):
    """Service discovery sui floating IP, visti da fuori.

    È la "vista esterna": scansioniamo i floating IP dalla namespace radice, da
    cui il nodo raggiunge la rete public. targets sono i floating IP (già nel
    perimetro). Ritorna lo stesso dizionario {ip: [servizi]}.
    """
    if not targets:
        return {}
    scope = conf.CONF.scanner.service_scan_scope
    LOG.info("service discovery esterno su %d floating IP, profondità '%s'",
             len(targets), scope)
    # namespace=None: nmap gira nella namespace radice (vedi privsep/discovery.py).
    nmap_xml = priv_discovery.service_scan_xml(None, list(targets), scope)
    return parse_services(nmap_xml)
