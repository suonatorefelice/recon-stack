# 0007 – Separazione dei privilegi con oslo.privsep

## Contesto

Il processo che riceve richieste HTTP non deve avere privilegi di root. Alcune operazioni dello scheduler, però, li richiedono: entrare in una network namespace esistente richiede la capability `CAP_SYS_ADMIN`, e alcune modalità di nmap usano socket raw (`CAP_NET_RAW`). Se un processo con questi privilegi avesse un difetto sfruttabile, la compromissione riguarderebbe l'intero nodo.

## Decisione

Applichiamo il principio del minimo privilegio:

* il processo web gira come utente non privilegiato e non esegue mai scansioni ([0004](0004-scheduler-separato.md));
* anche lo scheduler gira come utente non privilegiato;
* le sole operazioni privilegiate sono funzioni Python dichiarate con **oslo.privsep**: un demone privilegiato separato le esegue su richiesta dello scheduler, tramite un socket Unix. Il demone espone solo quelle funzioni, con argomenti controllati, e non accetta comandi arbitrari.

## Alternative scartate

* **Tutto come root**: massima semplicità ma superficie di attacco enorme.
* **sudo dallo scheduler**: funziona, ma ogni comando lanciato tramite shell rischia l'iniezione di argomenti, e la regola sudo va scritta con molta cura per non concedere più del necessario. oslo.privsep limita le operazioni a un insieme predefinito di funzioni ed è il meccanismo usato dai componenti OpenStack.

## Conseguenze accettate

* Architettura più complessa: un demone privilegiato in più, avviato da oslo.privsep.
* Va definita con cura la superficie delle operazioni privilegiate esposte, e va mantenuta piccola.
* `CAP_SYS_ADMIN` è una capability molto ampia, vicina a root: è il motivo per cui la confiniamo nel demone di privsep invece di darla a un processo intero.

## Fonti

* oslo.privsep: https://docs.openstack.org/oslo.privsep/latest/
* setns(2), privilegi necessari per entrare in una namespace: https://man7.org/linux/man-pages/man2/setns.2.html
* capabilities(7): https://man7.org/linux/man-pages/man7/capabilities.7.html
