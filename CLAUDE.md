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
5. API REST: GET /services?name=..., /hosts, /hosts/{id}
6. Scoperta periodica (APScheduler) + diff con la scansione precedente + storico
7. Esposizione: interno vs floating IP, confronto con SG (latente / regola inutile)
8. Mappa topologia (Graphviz) e report HTML/PDF con modalità condivisibile (redaction)

## Vincoli di sicurezza (obbligatori)
- Scansionare SOLO IP appartenenti alle subnet del progetto in Neutron
- Rate limiting delle scansioni; avvio scansioni solo da admin
- Log di ogni scansione (chi, quando, perimetro)

## Stack tecnico
Python, Flask, APScheduler, openstacksdk (cloud "devstack-admin" da
/etc/openstack/clouds.yaml), python-nmap, SQLAlchemy + SQLite, Graphviz, Jinja2.
Porta interfaccia: 5238.

## Struttura repo
devstack/{settings,plugin.sh}  app/{app.py,inventory.py,discovery.py,catalog.py,
reconcile.py,scheduler.py,api.py,report/,templates/}  demo/setup_demo.sh
requirements.txt  README.md

## Plugin DevStack
- install: pip_install requirements, install_package nmap graphviz
- extra: run_process recon-stack "<python> app/app.py"
- unstack: stop_process recon-stack
- Attivazione: enable_plugin recon-stack https://github.com/suonatorefelice/recon-stack main

## Note tecniche
- Reti private dei tenant: scansione interna tramite namespace di rete Neutron sull'host
  (verificare il comportamento con il driver di rete in uso, OVN o OVS)
- Vista esterna: scansione dei floating IP dalla rete public
- Sviluppare lanciando Flask a mano; usare unstack/stack solo per verificare il plugin

## Regole di lavoro
- Procedere per fasi, verificare ogni fase prima della successiva
- Commit piccoli e frequenti con messaggi chiari
- Non eseguire scansioni fuori dal perimetro del progetto
