# Service discovery: scoprire quali programmi sono in ascolto su un host (Step 7).
#
# Dopo l'host discovery (Step 6, scanner/discovery.py), che dice QUALI indirizzi
# rispondono, il service discovery dice COSA gira su quegli indirizzi: per ogni
# porta aperta il servizio (es. ssh), il prodotto (es. OpenSSH) e la versione.
# Lo fa nmap con l'opzione -sV.
#
# Come per l'host discovery, la parte che richiede privilegi (entrare nel
# namespace ed eseguire nmap) è isolata in privsep/discovery.py (ADR 0007); qui,
# senza privilegi, facciamo due cose testabili senza OpenStack:
#   - parse_services: leggere l'XML prodotto da nmap e ricavarne, per ogni IP,
#     l'elenco dei servizi trovati sulle porte aperte;
#   - discover_services: entrare nella namespace della rete (tramite la funzione
#     privilegiata) ed eseguire la scansione sugli indirizzi indicati.
#
# I servizi finiscono nella tabella services (models.Service): porta, protocollo
# (tcp/udp), nome, prodotto, versione. La "vista" è sempre interna (VIEW_INTERNAL)
# perché scansioniamo dalla rete del progetto; la vista esterna sui floating IP
# arriva allo Step 11.

import logging
from xml.etree import ElementTree

from recon_stack import conf
from recon_stack.privsep import discovery as priv_discovery
from recon_stack.scanner import namespaces

LOG = logging.getLogger(__name__)


def parse_services(nmap_xml):
    """Ricava dall'XML di nmap i servizi trovati, raggruppati per indirizzo IP.

    Struttura dell'XML di nmap: un <host> per indirizzo, con un <address> e, se
    sono state esaminate le porte, un blocco <ports> con un <port> per porta.
    Ogni <port> ha uno <state> (ci interessano solo quelle "open") e di solito
    un <service> con nome, prodotto e versione (gli attributi mancanti restano
    None: nmap non sempre riesce a riconoscere tutto).

    Restituisce un dizionario {ip: [ {port_number, protocol, name, product,
    version}, ... ]}. Gli IP senza porte aperte non compaiono.
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
                # Ci interessano solo le porte davvero aperte: le "closed" e le
                # "filtered" non ospitano un servizio raggiungibile.
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


def discover_services(network_id, targets, driver=None):
    """Esegue il service discovery su una rete e restituisce i servizi per IP.

    - network_id: la rete da scansionare (decide la namespace, ADR 0006);
    - targets: gli indirizzi su cui cercare i servizi, cioè gli host che hanno
      risposto all'host discovery (censiti + sconosciuti), già dentro il
      perimetro verificato da chi ci chiama;
    - driver: driver di rete; se None si usa quello in configurazione.

    Se non ci sono bersagli non entra nemmeno nel namespace. La profondità
    (quante porte) viene dall'opzione [scanner] service_scan_scope.
    """
    if not targets:
        return {}
    namespace = namespaces.internal_namespace(network_id, driver)
    scope = conf.CONF.scanner.service_scan_scope
    LOG.info("service discovery nella rete %s (namespace %s): %d host, "
             "profondità '%s'", network_id, namespace, len(targets), scope)
    nmap_xml = priv_discovery.service_scan_xml(namespace, list(targets), scope)
    return parse_services(nmap_xml)
