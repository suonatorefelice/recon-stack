# 0005 – Perimetro dalle subnet Neutron, ricalcolato a ogni scansione

## Contesto

Dobbiamo decidere quali indirizzi scansionare, e un vincolo del progetto impone di scansionare solo indirizzi che appartengono al progetto. Una lista fissa in un file è semplice ma fragile: ogni nuova subnet richiede un intervento manuale, e una subnet cancellata e riassegnata a un altro progetto resterebbe nella lista.

## Decisione

All'inizio di ogni scansione interroghiamo Neutron e ricaviamo il perimetro del progetto:

* **vista interna**: le subnet delle reti del progetto, di cui si usano gli indirizzi utilizzabili (esclusi indirizzo di rete e broadcast);
* **vista esterna**: i soli floating IP associati alle porte del progetto. Le reti condivise, come `public`, non entrano nel perimetro per intero.

Un solo punto del codice verifica che ogni bersaglio appartenga al perimetro prima di passarlo a nmap; un bersaglio fuori perimetro fa fallire la scansione invece di essere saltato in silenzio. Il perimetro effettivo usato viene scritto nel log della scansione.

## Alternative scartate

* **File statico di subnet**: va mantenuto a mano e si disallinea dalla realtà del cloud.
* **Calcolare il perimetro una volta e riusarlo**: una subnet nuova resterebbe fuori, e una subnet rimossa resterebbe dentro anche dopo essere passata a un altro progetto. Ricalcolarlo a ogni scansione è più semplice e corretto.

## Conseguenze accettate

* Ogni scansione richiede una chiamata a Neutron: costo trascurabile rispetto alla durata della scansione stessa.
* Se Neutron è irraggiungibile, la scansione non parte: meglio fallire che scansionare un perimetro sbagliato.
* Le subnet molto grandi (ad esempio /16) richiedono un limite configurabile, per non generare scansioni interminabili.

## Fonti

* Neutron API: https://docs.openstack.org/api-ref/network/v2/
* Nmap target specification: https://nmap.org/book/man-target-specification.html
