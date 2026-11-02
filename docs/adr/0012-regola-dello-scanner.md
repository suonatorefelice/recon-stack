# 0012 – Regola dello scanner per vedere i servizi latenti

## Contesto

Un **servizio latente** è un programma in ascolto su una porta che il security group non apre: oggi nessuno lo raggiunge, ma basta una regola nuova per esporlo (vedi il [glossario](../../GLOSSARY.md)). L'ADR [0011](0011-esposizione-e-segnalazioni.md) prevedeva di segnalarlo confrontando i servizi trovati con le regole.

Il test su DevStack del 2 novembre 2026 ha mostrato che così non può funzionare. Il security group filtra anche il traffico che parte dalla network namespace da cui scansioniamo ([0006](0006-vista-interna-namespace.md)). Un servizio di prova sulla porta 9090, che il security group della demo non apre, risultava `filtered`. Con una regola temporanea che apriva la 9090 al solo indirizzo della namespace risultava `open`, e tolta la regola tornava `filtered`. Lo scanner vede quindi la rete esattamente come qualunque altra macchina: ciò che il security group blocca, a lui resta invisibile. Senza un agente nella VM ([0003](0003-scoperta-senza-agenti.md)) un servizio latente non si può scoprire.

## Decisione

**Chi amministra il progetto può aggiungere al security group una "regola dello scanner"**: una regola in ingresso che apre le porte (anche tutte) **al solo indirizzo da cui parte la scansione**, scritto come `/32`. Quell'indirizzo è quello della porta Neutron a cui appartiene la namespace: la porta dei metadati di OVN (`network:distributed`) o quella del DHCP con OVS (`network:dhcp`).

Recon-Stack riconosce queste regole confrontando il loro `remote_ip_prefix` con gli indirizzi di quelle porte, letti dall'inventario, e le **mette da parte** nel calcolo dell'esposizione:

* non contano come "previsione" di un servizio: un servizio raggiungibile **solo** grazie alla regola dello scanner viene segnalato come latente;
* non vengono segnalate come regole inutili, anche se aprono porte su cui non ascolta niente.

La regola la aggiunge l'amministratore, non il programma: Recon-Stack resta in sola lettura su OpenStack ([architettura](../architettura.md#confini)). Lo script demo la crea, così il caso si può mostrare.

## Alternative scartate

* **Dichiarare il limite e basta.** Onesto, ma toglie una delle segnalazioni più utili, quella del servizio pronto a essere esposto per errore.
* **Far aggiungere la regola a Recon-Stack, per la durata della scansione.** Funzionerebbe senza chiedere niente all'amministratore, ma il servizio diventerebbe uno strumento che modifica il firewall dei progetti. Si perde la garanzia di sola lettura, e un errore o un'interruzione a metà lascerebbe una regola aperta.
* **Un agente nella VM**, che elenca i processi in ascolto. Scartato in [0003](0003-scoperta-senza-agenti.md).

## Conseguenze accettate

* I servizi latenti si vedono solo nei progetti in cui l'amministratore ha aggiunto la regola dello scanner. Senza, il servizio latente non compare, e la documentazione lo dice.
* La regola apre davvero le porte all'indirizzo della namespace: chi controlla il nodo DevStack può già raggiungere quella namespace, quindi non si allarga la superficie verso l'esterno, ma va tenuto presente.
* Con OVN l'indirizzo dello scanner è di solito il secondo della subnet (es. `10.10.10.2`), ma non è garantito: va letto dalla porta dei metadati, come fa lo script demo.

## Fonti

* Esito delle prove su DevStack: [architettura, "Verifiche su DevStack"](../architettura.md#verifiche-su-devstack)
* Regole dei security group e `remote_ip_prefix`: https://docs.openstack.org/api-ref/network/v2/#security-group-rules-security-group-rules
* Metadati con OVN (porta `network:distributed`): https://docs.openstack.org/neutron/latest/contributor/internals/ovn/metadata_api.html
