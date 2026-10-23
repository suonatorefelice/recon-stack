# Calcolo e controllo del perimetro di una scansione (ADR 0005).
#
# Il perimetro è l'insieme degli indirizzi che la scansione PUÒ toccare. Un
# vincolo del progetto (CLAUDE.md) impone di scansionare solo indirizzi che
# appartengono al progetto: il perimetro serve esattamente a questo, ed è un
# punto solo del codice a deciderlo, così la regola non si può aggirare.
#
# Si compone di due parti (ADR 0005):
#   - vista interna: gli indirizzi utilizzabili delle subnet delle reti del
#     progetto (esclusi indirizzo di rete e di broadcast);
#   - vista esterna: i soli floating IP del progetto (non l'intera rete public).
#
# Lo ricalcoliamo a ogni scansione leggendo Neutron: una subnet nuova entra da
# sola, una rimossa esce da sola. Se Neutron è irraggiungibile la scansione non
# parte: meglio fallire che scansionare un perimetro sbagliato.
#
# Un IP di un altro progetto non appartiene a nessuna di queste subnet e non è
# fra i floating IP del progetto: quindi risulta fuori perimetro e viene
# rifiutato, come richiede lo Step 5.

import ipaddress
import logging

from recon_stack import conf

LOG = logging.getLogger(__name__)


class PerimeterError(Exception):
    """Un bersaglio è fuori dal perimetro consentito.

    Porta con sé l'elenco degli indirizzi incriminati, così il log della
    scansione può dire con precisione cosa è stato rifiutato.
    """

    def __init__(self, targets):
        self.targets = list(targets)
        super().__init__(
            "indirizzi fuori perimetro: " + ", ".join(self.targets))


class PerimeterTooLargeError(Exception):
    """Il perimetro ha più indirizzi del limite configurato.

    Le subnet molto grandi (es. /16) genererebbero scansioni interminabili
    (ADR 0005): meglio fermarsi subito e chiedere di restringere.
    """


def _usable_in(net):
    """Quanti indirizzi utilizzabili ha una rete (esclusi rete e broadcast)."""
    # Per /31 e /32 non esistono indirizzo di rete e broadcast riservati:
    # tutti gli indirizzi sono utilizzabili.
    if net.prefixlen >= net.max_prefixlen - 1:
        return net.num_addresses
    return net.num_addresses - 2


def _is_usable(ip, net):
    """L'indirizzo ip è uno degli indirizzi utilizzabili della rete net?"""
    if ip not in net:
        return False
    if net.prefixlen >= net.max_prefixlen - 1:
        return True
    return ip != net.network_address and ip != net.broadcast_address


class Perimeter:
    """Il perimetro di una scansione: subnet interne e floating IP esterni."""

    def __init__(self, internal_subnets, floating_ips):
        # internal_subnets: lista di dizionari {subnet_id, network_id, cidr}.
        # floating_ips: insieme di indirizzi (stringhe).
        self.internal_subnets = internal_subnets
        self.floating_ips = set(floating_ips)
        # Precalcoliamo gli oggetti rete, una volta sola: il controllo di
        # appartenenza (contains) viene chiamato per ogni bersaglio.
        self._nets = [ipaddress.ip_network(s["cidr"]) for s in internal_subnets]

    @property
    def usable_internal_addresses(self):
        """Numero totale di indirizzi interni utilizzabili."""
        return sum(_usable_in(net) for net in self._nets)

    def contains(self, ip_address):
        """L'indirizzo è dentro il perimetro (interno o floating IP)?"""
        if ip_address in self.floating_ips:
            return True
        ip = ipaddress.ip_address(ip_address)
        return any(_is_usable(ip, net) for net in self._nets)

    def check(self, targets):
        """Verifica che TUTTI i bersagli siano nel perimetro.

        Se anche uno solo è fuori, solleva PerimeterError con l'elenco: la
        scansione fallisce invece di saltarlo in silenzio (ADR 0005).
        """
        outside = [t for t in targets if not self.contains(t)]
        if outside:
            raise PerimeterError(outside)

    def hosts_by_network(self):
        """Indirizzi interni da provare, raggruppati per rete.

        Per ogni rete restituisce la lista degli indirizzi utilizzabili delle
        sue subnet (net.hosts() esclude già rete e broadcast). Serve all'host
        discovery (scanner/discovery.py), che entra una namespace per rete
        (ADR 0006) e prova gli indirizzi di quella rete.
        """
        result = {}
        for subnet in self.internal_subnets:
            net = ipaddress.ip_network(subnet["cidr"])
            addresses = result.setdefault(subnet["network_id"], [])
            addresses.extend(str(host) for host in net.hosts())
        return result

    def as_dict(self):
        """Riepilogo serializzabile, da salvare nel log della scansione.

        Finisce nella colonna scans.perimeter (testo JSON): così il log dice
        sempre su quale perimetro una scansione si è basata.
        """
        return {
            "internal_subnets": self.internal_subnets,
            "floating_ips": sorted(self.floating_ips),
            "usable_internal_addresses": self.usable_internal_addresses,
        }


def build(conn, project_id):
    """Calcola il perimetro del progetto leggendo Neutron.

    conn è la connessione a OpenStack (scanner/cloud.py); la riceviamo
    dall'esterno così i test passano una connessione finta.
    """
    internal_subnets = [
        {"subnet_id": subnet.id,
         "network_id": subnet.network_id,
         "cidr": subnet.cidr}
        for subnet in conn.network.subnets(project_id=project_id)
    ]
    floating_ips = {
        fip.floating_ip_address
        for fip in conn.network.ips(project_id=project_id)
        if fip.floating_ip_address
    }

    perimeter = Perimeter(internal_subnets, floating_ips)

    limit = conf.CONF.scanner.max_perimeter_addresses
    if perimeter.usable_internal_addresses > limit:
        raise PerimeterTooLargeError(
            f"il perimetro ha {perimeter.usable_internal_addresses} indirizzi "
            f"interni, oltre il limite di {limit} "
            f"(opzione [scanner] max_perimeter_addresses)")

    LOG.info("perimetro del progetto %s: %d subnet, %d indirizzi interni, "
             "%d floating IP", project_id, len(internal_subnets),
             perimeter.usable_internal_addresses, len(floating_ips))
    return perimeter
