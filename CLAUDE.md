# Recon-Stack

Plugin DevStack per OpenStack: service discovery automatico senza agenti.
Progetto d'esame (Magistrale Sicurezza Informatica e Tecnologie Cloud, UNISA).

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
- 0001 Scoperta senza agenti: API OpenStack (dichiarato) + scansione (reale)
- 0002 Perimetro = subnet Neutron del progetto, ricalcolato a ogni scansione
- 0003 Scansione interna dai namespace di rete Neutron sull'host
- 0004 Separazione dei privilegi: recon-api senza privilegi, recon-scanner unico
  processo che usa sudo, e solo tramite un wrapper che accetta argomenti fissi
- 0005 Database MySQL di DevStack (SQLAlchemy + alembic); SQLite solo nei test
- 0006 Autenticazione con token Keystone (keystonemiddleware); scansioni solo con ruolo admin
- 0007 Servizio in stile OpenStack: pacchetto pbr, oslo.config, uwsgi sulla porta 5238
- 0008 Scansioni eseguite dal processo recon-scanner con APScheduler; le richieste
  passano dal database

## Stack tecnico
Python, Flask, APScheduler, openstacksdk (cloud "devstack-admin" da
/etc/openstack/clouds.yaml), python-nmap, SQLAlchemy + alembic, oslo.config,
keystonemiddleware, uwsgi, Graphviz, Jinja2. Porta interfaccia: 5238.

## Struttura repo
```
devstack/{settings,plugin.sh}     plugin DevStack
recon_stack/                      pacchetto Python del servizio
  api/        app Flask, API REST /v1, dashboard
  scanner/    inventario, perimetro, discovery, riconciliazione, scheduler
  db/         modelli, accesso ai dati, migrazioni alembic
  report/     mappa Graphviz e report
  templates/  pagine Jinja2
  tests/      unit/ (tox, senza OpenStack) e tempest/ (su DevStack)
tools/recon-stack-netns-scan      wrapper eseguito con sudo dallo scanner
etc/                              configurazione di esempio
demo/setup_demo.sh                crea un progetto demo da scansionare
docs/                             architettura, api, concetti, piano, adr/, img/
README.md GLOSSARY.md setup.cfg setup.py requirements.txt tox.ini
```

## Plugin DevStack
- install: setup_develop del pacchetto, install_package nmap graphviz, wrapper + regola sudo
- post-config: file di configurazione, database e migrazioni, servizio ed endpoint in Keystone
- extra: run_process recon-api (uwsgi :5238) e recon-scanner
- unstack: stop_process; clean: rimozione configurazione
- Attivazione: enable_plugin recon-stack https://github.com/suonatorefelice/recon-stack main

## Note tecniche
- Reti private dei tenant: scansione interna tramite namespace di rete Neutron sull'host
  (OVN: ovnmeta-<id rete>; OVS: qdhcp-<id rete>). Da verificare su DevStack: quanto i
  security group filtrano il traffico che parte dal namespace
- Vista esterna: scansione dei floating IP dalla rete public
- Sviluppare lanciando Flask a mano; usare unstack/stack solo per verificare il plugin

## Regole di lavoro
- Procedere per fasi (docs/piano.md), verificare ogni fase prima della successiva
- L'autore ha basi minime su OpenStack: spiegare in italiano semplice ogni concetto e ogni scelta
- Ogni decisione di forma ha un ADR in docs/adr/ (contesto, decisione, alternative, conseguenze, fonti)
- Codice commentato: ogni modulo apre con un commento che dice cosa fa e perché; i
  passaggi non ovvi sono spiegati, citando l'ADR quando serve
- Commit piccoli, in italiano, con prefisso (feat/fix/docs/test/chore) e riferimento (#1);
  nessuna riga di attribuzione all'AI
- Non eseguire scansioni fuori dal perimetro del progetto
