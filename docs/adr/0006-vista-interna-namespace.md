# 0006 – Vista interna dalle network namespace di Neutron

## Contesto

DevStack crea reti private per le VM, ma il nodo host non ha un'interfaccia direttamente collegata a quelle reti. Le VM sono raggiungibili tramite floating IP, ma non vogliamo assegnare un floating IP a ogni istanza solo per scansionarla: esaurirebbe il range e cambierebbe la configurazione delle VM.

## Decisione

Usiamo le network namespace di Linux che Neutron crea già sul nodo. Il nome dipende dal driver di rete in uso:

* con **OVN**, il predefinito nelle versioni recenti di DevStack, c'è una namespace `ovnmeta-<id rete>` per ogni rete, usata per il servizio dei metadati;
* con **OVS** ci sono `qdhcp-<id rete>` per il DHCP e `qrouter-<id router>` per i router.

Lo scanner esegue nmap dentro la namespace collegata alla rete da scansionare (`ip netns exec <namespace> nmap ...`). Quale driver è in uso si verifica sul nodo con `sudo ip netns list`.

## Alternative scartate

* **Collegare `br-ex` a un'interfaccia fisica**: esporrebbe le reti private sulla LAN, cambiando il modello di isolamento di DevStack.
* **Floating IP per ogni VM**: richiederebbe di assegnare un IP pubblico a ogni istanza, esaurendo il range.

## Conseguenze accettate

* Entrare in una namespace di rete richiede privilegi elevati: come li confiniamo è in [0007](0007-privilegi-oslo-privsep.md).
* La configurazione è specifica di DevStack/Linux e andrà adattata in altri ambienti.
* Dipendiamo dalla topologia di Neutron e dal driver di rete: se cambia il modo in cui vengono create le namespace, va rivisto.

## Fonti

* network_namespaces(7): https://manpages.debian.org/bookworm/manpages/network_namespaces.7.en.html
* ip-netns(8): https://man7.org/linux/man-pages/man8/ip-netns.8.html
* Metadati con OVN in Neutron: https://docs.openstack.org/neutron/latest/contributor/internals/ovn/metadata_api.html
