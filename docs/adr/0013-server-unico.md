# 0013 – Server unico: un client (Horizon) e un solo server

## Contesto

La [0004](0004-scheduler-separato.md) separava l'API dallo scheduler, per evitare scheduler duplicati con più processi web. Per un servizio che gira su un nodo solo ed esegue una scansione alla volta, la divisione costa più di quanto rende: due servizi da avviare e controllare, e una coda di richieste nel database letta a intervalli, con qualche secondo di ritardo fra la richiesta e l'inizio della scansione.

Il progetto è un sistema **client-server**: un solo client, la dashboard Horizon ([0010](0010-dashboard-plugin-horizon.md)), parla con un solo server. La API `/v1` resta raggiungibile anche con `curl` e un token Keystone.

## Decisione

* **Un solo server** (il servizio `devstack@recon-api`): uwsgi sulla porta 5238 con `processes=1` e `enable-threads`. Serve la API `/v1`, esegue le scansioni e le pianifica.
* **`POST /v1/scans` avvia un thread in background** e risponde subito `202 Accepted`; il client segue l'avanzamento con `GET /v1/scans/<id>` (polling su stato e fase).
* **Scheduler interno**: un APScheduler dentro il processo esegue le scansioni periodiche dei progetti in `[scanner] periodic_projects`. Con un solo processo non ci sono scheduler duplicati, il problema da cui nasceva la 0004.
* **I privilegi restano confinati in privsep ([0007](0007-privilegi-oslo-privsep.md)).** Il server gira come utente non privilegiato; le funzioni che entrano nelle namespace ed eseguono nmap girano nel demone privsep, un processo figlio che il server avvia da sé e chiama via socket Unix privato.
* **Il report è una pagina stampabile della dashboard**, costruita dalle rotte `/v1` (scansione, segnalazioni, host e servizi): il server non produce documenti.
* **MySQL è l'archivio privato del server** ([0001](0001-database-mysql.md)): la dashboard non lo legge mai, passa dalla API.

Questa ADR **supera la 0004** e **integra la 0008** (`processes=1`, thread, scheduler interno).

## Alternative scartate

* **API e scheduler in due processi (la 0004)**: raddoppia le parti da gestire e da spiegare, senza benefici su un nodo solo.
* **Più processi uwsgi**: ogni processo avrebbe il suo scheduler e le scansioni verrebbero duplicate; per questo `processes=1`, con `lazy-apps` perché lo scheduler parta nel worker che serve le richieste.
* **Capability sul server invece di privsep**: dare `CAP_SYS_ADMIN` e `CAP_NET_RAW` direttamente al processo uwsgi (con un drop-in systemd) e fare a meno di privsep. Provata su DevStack e scartata: con OVN `ip netns exec` risponde `Operation not permitted` anche con le capability, perché entrare nella namespace richiede root, che solo il demone privsep ha. In più darebbe una capability molto ampia al processo che riceve le richieste HTTP.
* **Code di lavoro esterne (Celery, RabbitMQ)**: un componente pesante per una sola scansione alla volta.

## Conseguenze accettate

* Il server che riceve le richieste HTTP resta non privilegiato, ma su DevStack, dove `stack` ha `sudo NOPASSWD:ALL`, questo **non** impedisce a chi controlla il server di diventare root: privsep restringe i comandi root del codice, non è un confine contro una compromissione totale (modello di minaccia nella [0007](0007-privilegi-oslo-privsep.md)).
* Le scansioni in corso si interrompono se il servizio si riavvia: all'avvio successivo quelle rimaste `RUNNING` o `PENDING` vengono chiuse come `FAILED`.
* Una scansione lunga condivide il processo con la API, quindi pesa anche sui suoi tempi di risposta.
* Un solo servizio da gestire (`devstack@recon-api`), più la regola sudoers e il socket di privsep, piccoli e confinati.

## Fonti

* oslo.privsep: https://docs.openstack.org/oslo.privsep/latest/
* APScheduler: https://apscheduler.readthedocs.io/
* uwsgi, `enable-threads` e `lazy-apps`: https://uwsgi-docs.readthedocs.io/en/latest/ThingsToKnow.html
