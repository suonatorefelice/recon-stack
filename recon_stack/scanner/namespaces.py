# Nome della network namespace in cui entrare per scansionare una rete (ADR 0006).
#
# Il nodo DevStack non ha un'interfaccia diretta sulle reti private dei progetti,
# ma Neutron crea sul nodo delle "network namespace" (ambienti di rete isolati
# del kernel Linux) collegate a quelle reti. Per vedere una rete dall'interno si
# esegue il comando dentro la sua namespace (ip netns exec <namespace> ...).
#
# Il nome della namespace dipende dal driver di rete in uso (opzione
# [scanner] network_driver), non da noi: lo decide Neutron.

from recon_stack import conf

DRIVER_OVN = "ovn"
DRIVER_OVS = "ovs"


def internal_namespace(network_id, driver=None):
    """Nome della namespace collegata alla rete da scansionare.

    - OVN (predefinito in DevStack recenti): ogni rete ha una namespace
      'ovnmeta-<id rete>', usata per il servizio dei metadati.
    - OVS: la namespace del DHCP, 'qdhcp-<id rete>', è attestata sulla rete.

    Se driver è None si usa quello in configurazione.
    """
    if driver is None:
        driver = conf.CONF.scanner.network_driver
    if driver == DRIVER_OVN:
        return f"ovnmeta-{network_id}"
    if driver == DRIVER_OVS:
        return f"qdhcp-{network_id}"
    # choices in conf.py impedisce già altri valori da file; questo protegge
    # chi chiama la funzione passando un driver a mano.
    raise ValueError(f"driver di rete sconosciuto: {driver}")
