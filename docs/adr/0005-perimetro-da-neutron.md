# 0005 – Perimetro dalle subnet Neutron, ricalcolato a ogni scansione

## Contesto

Dobbiamo decidere quali indirizzi scansionare, e un vincolo del progetto impone di scansionare solo indirizzi che appartengono al progetto. Una lista fissa in un file è semplice ma fragile: ogni nuova subnet richiede un intervento manuale, e una subnet cancellata e riassegnata a un altro progetto resterebbe nella lista.

## Decisione

All'inizio di ogni scansione interroghiamo Neutron e ricaviamo il perimetro del progetto:

* **vista interna**: le subnet delle reti del progetto, di cui si usano gli indirizzi utilizzabili (esclusi indirizzo di rete e broadcast);
* **vista esterna**: i floating IP del progetto, letti dall'inventario. Le reti condivise, come `public`, non entrano nel perimetro per intero.

Il perimetro **determina quali indirizzi scansionare**: i bersagli interni sono generati dal perimetro stesso (gli indirizzi utilizzabili delle subnet del progetto), quindi non possono cadere fuori per costruzione, e un secondo controllo di appartenenza a ridosso di nmap non aggiungerebbe nulla. Il perimetro impone comunque un limite alla dimensione (`max_perimeter_addresses`): le subnet troppo grandi fanno fallire la scansione prima di generare bersagli interminabili. Il perimetro effettivo usato viene scritto nel log della scansione.

Il controllo che protegge davvero il comando nmap sta invece **nel confine privsep** ([0007](0007-privilegi-oslo-privsep.md)): lì ogni bersaglio viene validato come indirizzo IP sintatticamente valido (`ipaddress.ip_address`) prima di costruire la riga di comando. È l'ultima barriera prima di root, dove conta di più.

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
