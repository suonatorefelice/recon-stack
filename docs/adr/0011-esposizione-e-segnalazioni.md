# 0011 – Esposizione: vista esterna e segnalazioni confrontate con i security group

## Contesto

Gli step precedenti dicono quali host e servizi esistono nelle reti del progetto (vista interna, dai namespace di Neutron, [0006](0006-vista-interna-namespace.md)). Mancava però la domanda che interessa a chi amministra il cloud: *quanto* di tutto questo è davvero esposto, e le regole del firewall (security group) sono coerenti con i servizi che girano? Lo step 11 aggiunge questa lettura. È uno strumento difensivo di inventario, provato solo sul progetto demo in laboratorio (CLAUDE.md).

## Decisione

Tre scelte, tutte in sola lettura su OpenStack (ADR [0003](0003-scoperta-senza-agenti.md)):

* **Inventario dei security group.** All'inizio della scansione leggiamo da Neutron i security group del progetto, le loro regole e quali porte (e quindi VM) li applicano. Finiscono nelle tabelle `inventory_security_groups` e `inventory_sg_rules`, come il resto dell'inventario.
* **Vista esterna.** Oltre alla vista interna, cerchiamo i servizi sui soli floating IP del progetto (già parte del perimetro, ADR [0005](0005-perimetro-da-neutron.md)) dalla rete `public`. Il nodo DevStack la raggiunge direttamente, quindi questa scansione gira nella namespace radice dell'host, non in una namespace di progetto. Resta confinata nel demone privilegiato come le altre ([0007](0007-privilegi-oslo-privsep.md)).
* **Segnalazioni salvate.** Il confronto fra i servizi trovati e le regole produce delle segnalazioni (`exposure_findings`), ognuna con tipo, gravità e una spiegazione in italiano: regola inutile, servizio latente, esposizione eccessiva, host non censito esposto, floating IP inutile, più le conferme dalla vista esterna. Le salviamo nel database come gli altri risultati, così entrano nello storico e si possono rileggere da API, comando e dashboard.

## Alternative scartate

* **Calcolare le segnalazioni al volo a ogni richiesta**: più semplice, ma le perderemmo dallo storico e non sarebbero confrontabili fra scansioni; preferiamo salvarle, coerentemente con host e servizi.
* **Assegnare un floating IP a ogni VM per la vista esterna**: esaurirebbe il range e cambierebbe la configurazione delle VM; guardiamo solo i floating IP che esistono già.

## Conseguenze accettate

* La vista esterna dipende dal fatto che il nodo DevStack raggiunga la rete `public`: è vero nella configurazione standard, va verificato sul nodo.
* Le segnalazioni sono indizi per chi amministra, non verdetti: un servizio "latente" o una regola "inutile" vanno letti e valutati, non corretti in automatico (il servizio non modifica mai nulla).

## Fonti

* Security groups in Neutron: https://docs.openstack.org/neutron/latest/admin/archives/introduction.html#security-groups
* openstacksdk, security group rules: https://docs.openstack.org/openstacksdk/latest/user/resources/network/v2/security_group_rule.html
