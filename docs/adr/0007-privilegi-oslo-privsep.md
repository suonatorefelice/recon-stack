# 0007 – Separazione dei privilegi con oslo.privsep

## Contesto

Il processo che riceve richieste HTTP non deve avere privilegi di root. Una parte delle scansioni, però, li richiede: entrare in una network namespace con `ip netns exec` richiede root (su DevStack non bastano le capability date al processo, come verificato nella [0013](0013-server-unico.md)), e alcune modalità di nmap usano socket raw. Se un processo con questi privilegi avesse un difetto sfruttabile, la compromissione riguarderebbe l'intero nodo.

## Decisione

Applichiamo il principio del minimo privilegio:

* il server (API, scheduler e thread di scansione, [0013](0013-server-unico.md)) gira come utente non privilegiato;
* le sole operazioni privilegiate sono funzioni Python dichiarate con **oslo.privsep** (`privsep/discovery.py`): un demone separato le esegue su richiesta del server, tramite un socket Unix privato. Il demone espone solo quelle funzioni, con argomenti controllati, e non accetta comandi arbitrari;
* il demone parte come root (via `sudo` e `privsep-helper`, con una regola sudoers scritta dal plugin DevStack) e subito dopo tiene solo le capability necessarie: `CAP_SYS_ADMIN` per entrare nelle namespace e `CAP_NET_RAW` per i socket raw di nmap.

Il confine privsep è anche il punto in cui si **validano gli input**: prima di costruire la riga di comando di nmap, ogni target viene verificato come indirizzo IP sintatticamente valido (`ipaddress.ip_address`, `_valida_target`) e la namespace deve avere esattamente la forma `ovnmeta-<uuid>` (`_valida_namespace`, UUID di Neutron con i trattini; è ammesso solo `None`, la namespace radice della vista esterna). È la barriera che protegge davvero il comando — l'ultima prima di root — ed è per questo che vive qui e non "a valle" a ridosso del perimetro ([0005](0005-perimetro-da-neutron.md)). Un valore diverso solleva `ValueError` e non arriva mai a `ip netns exec`.

## Modello di minaccia reale

Va detto con onestà cosa privsep protegge e cosa no.

* Su **DevStack** l'utente `stack` ha `sudo` con `NOPASSWD:ALL`. Chi compromettesse per intero il processo del server (che gira come `stack`) potrebbe già diventare root con `sudo`, senza passare da privsep. Quindi privsep **riduce** la superficie d'attacco ma **non la elimina**, e su DevStack **non è un confine di sicurezza rigido**.
* Il suo valore qui è un altro: le operazioni eseguite come root (nmap, `ip netns exec`) restano dietro una **API stretta di funzioni tipizzate** (`@entrypoint`) con **input validati** (target IP, namespace `ovnmeta-<uuid>`), invece di una shell o di comandi arbitrari. Un difetto nel codice che costruisce gli argomenti, o dati sporchi provenienti da OpenStack, non possono iniettare opzioni o percorsi nel comando eseguito come root.
* Su un'installazione di produzione, dove l'utente di servizio non ha `sudo` libero, lo stesso confine diventa un vero limite di privilegio.

## Alternative scartate

* **Tutto come root**: massima semplicità ma superficie di attacco enorme.
* **sudo dal server**: funziona, ma ogni comando lanciato tramite shell rischia l'iniezione di argomenti, e la regola sudo va scritta con molta cura per non concedere più del necessario. oslo.privsep limita le operazioni a un insieme predefinito di funzioni ed è il meccanismo usato dai componenti OpenStack.
* **rootwrap**: valutato e **non adottato**. È l'altro meccanismo OpenStack per i comandi privilegiati, ma funziona con filtri su righe di comando da mantenere in file a parte; abbiamo scelto gli entrypoint tipizzati di privsep con validazione degli input in Python, più semplici da testare (le funzioni di costruzione del comando sono pure) e già usati dai componenti OpenStack moderni. La scelta è documentata qui e non aggiunge un secondo meccanismo di privilegio.

## Conseguenze accettate

* Architettura più complessa: un demone privilegiato in più, avviato da oslo.privsep.
* Va definita con cura la superficie delle operazioni privilegiate esposte, e va mantenuta piccola.
* `CAP_SYS_ADMIN` è una capability molto ampia, vicina a root: è il motivo per cui la confiniamo nel demone di privsep invece di darla a un processo intero.

## Fonti

* oslo.privsep: https://docs.openstack.org/oslo.privsep/latest/
* setns(2), privilegi necessari per entrare in una namespace: https://man7.org/linux/man-pages/man2/setns.2.html
* capabilities(7): https://man7.org/linux/man-pages/man7/capabilities.7.html
