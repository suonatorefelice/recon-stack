# Perimetro di una scansione (ADR 0005): gli indirizzi che la scansione può
# toccare, ricalcolati ogni volta dalle risorse del progetto.
#   - Vista interna: gli indirizzi utilizzabili delle subnet del progetto
#     (esclusi rete e broadcast). Da qui nascono i bersagli dell'host discovery.
#   - Vista esterna: i floating IP del progetto, presi dall'inventario.
# Se il perimetro supera [scanner] max_perimeter_addresses la scansione non
# parte; se Neutron non risponde, la scansione fallisce.

import ipaddress
import logging

from recon_stack import conf

LOG = logging.getLogger(__name__)


class PerimeterTooLargeError(Exception):
    """Il perimetro ha più indirizzi del limite configurato (subnet troppo grandi)."""


def _usable_in(net):
    """Indirizzi utilizzabili di una rete (esclusi rete e broadcast)."""
    # /31 e /32 non hanno rete/broadcast riservati: tutti utilizzabili.
    if net.prefixlen >= net.max_prefixlen - 1:
        return net.num_addresses
    return net.num_addresses - 2


class Perimeter:
    """Il perimetro di una scansione: subnet interne e floating IP esterni."""

    def __init__(self, internal_subnets, floating_ips):
        # internal_subnets: dizionari {subnet_id, network_id, cidr}.
        # floating_ips: insieme di indirizzi (stringhe).
        self.internal_subnets = internal_subnets
        self.floating_ips = set(floating_ips)
        # Precalcoliamo gli oggetti rete (conteggio indirizzi e generazione bersagli).
        self._nets = [ipaddress.ip_network(s["cidr"]) for s in internal_subnets]

    @property
    def usable_internal_addresses(self):
        """Numero totale di indirizzi interni utilizzabili."""
        return sum(_usable_in(net) for net in self._nets)

    def hosts_by_network(self):
        """Indirizzi interni da provare, raggruppati per rete (net.hosts() esclude
        già rete e broadcast). Serve all'host discovery, una namespace per rete."""
        result = {}
        for subnet in self.internal_subnets:
            net = ipaddress.ip_network(subnet["cidr"])
            addresses = result.setdefault(subnet["network_id"], [])
            addresses.extend(str(host) for host in net.hosts())
        return result

    def as_dict(self):
        """Riepilogo serializzabile, salvato in scans.perimeter (testo JSON)."""
        return {
            "internal_subnets": self.internal_subnets,
            "floating_ips": sorted(self.floating_ips),
            "usable_internal_addresses": self.usable_internal_addresses,
        }


def build(conn, project_id, floating_ips):
    """Calcola il perimetro del progetto (conn iniettata per i test).

    Reti e subnet si leggono da Neutron; i floating IP arrivano già raccolti
    dall'inventario (inventory.collect), così Neutron li legge una volta sola.
    """
    # Le reti router:external (es. `public` di DevStack, del progetto admin)
    # non hanno una namespace ovnmeta-<rete>: le loro subnet restano fuori.
    external_networks = {
        network.id
        for network in conn.network.networks(project_id=project_id)
        if network.is_router_external
    }
    internal_subnets = [
        {"subnet_id": subnet.id,
         "network_id": subnet.network_id,
         "cidr": subnet.cidr}
        for subnet in conn.network.subnets(project_id=project_id)
        if subnet.network_id not in external_networks
    ]
    floating_addresses = {
        fip.floating_ip_address for fip in floating_ips
        if fip.floating_ip_address
    }

    perimeter = Perimeter(internal_subnets, floating_addresses)

    limit = conf.CONF.scanner.max_perimeter_addresses
    if perimeter.usable_internal_addresses > limit:
        raise PerimeterTooLargeError(
            f"il perimetro ha {perimeter.usable_internal_addresses} indirizzi "
            f"interni, oltre il limite di {limit} "
            f"(opzione [scanner] max_perimeter_addresses)")

    LOG.info("perimetro del progetto %s: %d subnet, %d indirizzi interni, "
             "%d floating IP", project_id, len(internal_subnets),
             perimeter.usable_internal_addresses, len(floating_addresses))
    return perimeter
