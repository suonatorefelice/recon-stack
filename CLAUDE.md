# Recon-Stack

Plugin DevStack per OpenStack: service discovery automatico senza agenti.
Progetto d'esame (Magistrale Sicurezza Informatica e Tecnologie Cloud, UNISA).

## Contesto d'uso
Progetto didattico, sviluppato e provato esclusivamente in laboratorio, su un'installazione
DevStack di proprietà dell'autore. Le scansioni riguardano solo VM e reti create a questo
scopo (demo/setup_demo.sh). È uno strumento difensivo di inventario: serve a chi amministra
il cloud per sapere cosa gira nelle proprie reti.

## Obiettivo
Scoprire host e servizi attivi nelle reti di un progetto OpenStack (porte, servizio,
versione), associarli alle risorse Nova/Neutron e pubblicarli in un catalogo
interrogabile via dashboard e API REST, con scoperta periodica e storico dei cambiamenti.

## Funzionalità (in ordine di priorità)
1. Inventario da API (Nova, Neutron): VM, IP, floating IP, porte, security group
2. Host discovery nelle reti del progetto; host non censiti marcati "sconosciuto"
3. Service discovery con nmap -sV (porta, protocollo, servizio, versione)
4. Catalogo servizi + ricerca (per servizio, host, rete, versione)
5. API REST: GET /v1/services?name=..., /v1/hosts, /v1/hosts/{id}
6. Scoperta periodica (APScheduler) + diff con la scansione precedente + storico
7. Esposizione: interno vs floating IP, confronto con SG (latente / regola inutile)
8. Mappa topologia (Graphviz) e report HTML/PDF con modalità condivisibile (redaction)

## Vincoli di sicurezza (obbligatori)
- Scansionare SOLO IP appartenenti alle subnet del progetto in Neutron
- Rate limiting delle scansioni; avvio scansioni solo da admin
- Log di ogni scansione (chi, quando, perimetro)

## Decisioni prese (motivate in docs/adr/)
- 0001 Database SQLite in modalità WAL, SQLAlchemy + Alembic; connessione in configurazione
- 0002 Autenticazione con token Keystone (keystonemiddleware); scansioni solo con ruolo admin
- 0003 Scoperta senza agenti: scanner sul nodo DevStack, fuori dalle VM
- 0004 Scheduler (APScheduler) in un processo separato dalla API; comunicano via database
- 0005 Perimetro dalle subnet Neutron del progetto + floating IP, ricalcolato a ogni scansione
- 0006 Vista interna dalle network namespace di Neutron (OVN: ovnmeta-; OVS: qdhcp-/qrouter-)
- 0007 Operazioni privilegiate solo tramite oslo.privsep; API e scheduler senza privilegi
- 0008 Flask + uwsgi in ascolto diretto sulla porta 5238, servizio `recon` nel catalogo Keystone
- 0009 Plugin DevStack `recon-stack` con fasi install, post-config, extra, unstack, clean
- 0010 Dashboard come plugin di Horizon (pannelli Django che chiamano la API /v1); recon-api resta solo API REST

## Stack tecnico
Python, Flask, APScheduler, openstacksdk (cloud "devstack-admin" da
/etc/openstack/clouds.yaml), python-nmap, SQLAlchemy + alembic, oslo.config,
keystonemiddleware, oslo.privsep, uwsgi, osc-lib (comandi `openstack recon`),
Horizon/Django (plugin della dashboard), Graphviz. Porta interfaccia: 5238.

## Struttura repo
```
devstack/{settings,plugin.sh}     plugin DevStack
recon_stack/                      pacchetto Python del servizio
  api/        app Flask, API REST /v1
  scanner/    inventario, perimetro, discovery, riconciliazione, scheduler
  privsep/    le sole funzioni eseguite con privilegi (oslo.privsep)
  db/         modelli, accesso ai dati, migrazioni alembic (SQLite)
  osc/        comandi `openstack recon ...` (plugin OpenStackClient)
  dashboard/  plugin Horizon: pannelli Django + file "enabled" + template
  report/     mappa Graphviz e report
  tests/      unit/ (tox, senza OpenStack) e tempest/ (su DevStack)
etc/                              configurazione di esempio
demo/setup_demo.sh                crea un progetto demo da scansionare
docs/                             architettura, api, concetti, piano, adr/, img/
README.md GLOSSARY.md setup.cfg setup.py requirements.txt tox.ini
```

## Plugin DevStack
- install: setup_develop del pacchetto, install_package nmap graphviz
- post-config: file di configurazione, database e migrazioni, utente di servizio,
  servizio ed endpoint in Keystone; installa i file "enabled" del plugin Horizon
  nella dashboard (ADR 0010) e la riavvia
- extra: run_process recon-api (uwsgi :5238) e recon-scanner
- unstack: stop_process; clean: rimozione configurazione e file "enabled" di Horizon
- Attivazione: enable_plugin recon-stack https://github.com/suonatorefelice/recon-stack main

## Note tecniche
- Reti private dei tenant: scansione interna tramite namespace di rete Neutron sull'host
  (OVN: ovnmeta-<id rete>; OVS: qdhcp-<id rete>). Da verificare su DevStack: quanto i
  security group filtrano il traffico che parte dal namespace
- Vista esterna: scansione dei floating IP dalla rete public
- Sviluppare lanciando Flask a mano; usare unstack/stack solo per verificare il plugin

## Regole di lavoro
- Procedere per fasi (docs/piano.md), verificare ogni fase prima della successiva
- Le scelte di forma sono negli ADR in docs/adr/: il codice deve rispettarle
- L'autore ha basi minime su OpenStack: spiegare in italiano semplice ogni concetto e ogni scelta
- Codice commentato: ogni modulo apre con un commento che dice cosa fa e perché; i
  passaggi non ovvi sono spiegati
- Commit piccoli, in italiano, con prefisso (feat/fix/docs/test/chore) e riferimento (#1);
  nessuna riga di attribuzione all'AI
- Non eseguire scansioni fuori dal perimetro del progetto
