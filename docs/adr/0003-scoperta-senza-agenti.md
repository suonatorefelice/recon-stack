# 0003 – Scoperta senza agenti: scansione dall'esterno delle VM

## Contesto

Dobbiamo scoprire cosa gira nelle VM. La scelta fondamentale: un agente dentro ogni VM, oppure una scansione dall'esterno. OpenStack sa quali VM esistono e a quali reti sono collegate, ma non sa cosa gira dentro.

## Decisione

Adottiamo un approccio senza agenti: lo scanner gira sul nodo DevStack, fuori dalle VM, e usa nmap per sondare le porte. Quali indirizzi sondare lo decide il perimetro ricavato da Neutron ([0005](0005-perimetro-da-neutron.md)).

## Alternative scartate

* **Agente in ogni VM**: va inserito nelle immagini, aggiornato e autenticato verso il servizio. Soprattutto, manca proprio dove servirebbe di più: una macchina sconosciuta o dimenticata non ha l'agente, e una macchina compromessa può farlo mentire.

## Conseguenze accettate

* Vediamo solo le porte raggiungibili in rete, non i processi interni né le vulnerabilità locali.
* La scansione è periodica, non in tempo reale.
* Dobbiamo gestire i risultati ambigui dovuti a firewall o a servizi che rispondono in modo poco chiaro.

## Fonti

* Nmap: https://nmap.org/book/man.html
