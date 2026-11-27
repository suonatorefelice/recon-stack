<p align="center">
  <img src="docs/img/recon-radar.svg" alt="Recon-Stack: un radar che scopre host e servizi nelle reti di un progetto" width="150">
</p>

<h1 align="center">Recon-Stack</h1>

<p align="center">
  <img alt="OpenStack: nuovo servizio" src="https://img.shields.io/badge/OpenStack-nuovo%20servizio-ED1944?logo=openstack&logoColor=white">
  <img alt="DevStack: plugin" src="https://img.shields.io/badge/DevStack-plugin-ED1944?logo=openstack&logoColor=white">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white">
  <img alt="Test unitari: 181" src="https://img.shields.io/badge/test%20unitari-181-22c55e">
  <br>
  <img alt="Integra: Keystone, Nova, Neutron, Horizon" src="https://img.shields.io/badge/integra-Keystone%20%C2%B7%20Nova%20%C2%B7%20Neutron%20%C2%B7%20Horizon-0f766e">
  <img alt="Interfacce: REST API, Horizon" src="https://img.shields.io/badge/interfacce-REST%20API%20%C2%B7%20Horizon-334155">
</p>

**Service discovery senza agenti per OpenStack.** Scopre quali host e quali servizi girano davvero nelle reti di un progetto, li confronta con ciò che OpenStack dichiara e li pubblica in un catalogo consultabile da API REST e dashboard, aggiornato periodicamente.

> Progetto didattico per il corso di laurea magistrale in Sicurezza Informatica e Tecnologie Cloud (UNISA), sviluppato e provato esclusivamente in laboratorio su un'installazione DevStack dell'autore. È uno strumento difensivo di inventario: le scansioni riguardano solo le reti del progetto a cui sono rivolte.

---

## Scheda

| | |
| --- | --- |
| **Tipo** | nuovo servizio OpenStack, installato come plugin DevStack |
| **Linguaggio** | Python |
| **Componenti integrati** | Keystone (autenticazione), Nova e Neutron (sola lettura), Horizon (dashboard) |
| **Interfacce** | API REST sulla porta 5238; l'unico client è la dashboard, un plugin di Horizon ([0013](docs/adr/0013-server-unico.md)) |
| **Strumenti** | nmap |

---

## Il problema

OpenStack sa **cosa è dichiarato**: quali VM esistono, che indirizzi hanno, quali porte apre il firewall. Non sa **cosa gira davvero**: se sulla porta 22 c'è OpenSSH e in che versione, se nella rete risponde un host che nessuno ha registrato, se una regola del firewall apre una porta su cui non ascolta niente.

Gli strumenti che OpenStack offre (Horizon, il DNS Designate, il progetto Searchlight, oggi ritirato) conoscono solo il dichiarato. Recon-Stack aggiunge l'osservato, senza installare niente dentro le VM.

## Cosa fa

- Legge da Nova e Neutron l'**inventario** del progetto: VM, porte, IP, floating IP, regole dei security group.
- Scopre gli **host attivi** nelle reti del progetto e segna come **sconosciuti** quelli che non hanno una porta Neutron.
- Scopre i **servizi** in ascolto: porta, protocollo, nome, versione.
- Li raccoglie in un **catalogo** per scansione e per progetto, con la ricerca dei servizi per nome.
- Ripete la scoperta **periodicamente** e mostra le **differenze** rispetto alla volta precedente.
- Distingue i servizi **interni** da quelli **esposti** tramite floating IP, e segnala le **regole di firewall inutili** e i **servizi latenti**.
- Produce un **report** stampabile (anche in PDF, dal browser) con le tabelle della scansione, delle segnalazioni, degli host e dei servizi.

## Vincoli di sicurezza

- Scansiona **solo** indirizzi delle subnet del progetto in Neutron e i suoi floating IP ([0005](docs/adr/0005-perimetro-da-neutron.md)).
- Le scansioni le avvia **solo chi ha il ruolo admin**, con un limite di frequenza ([0002](docs/adr/0002-autenticazione-keystone.md)).
- Ogni scansione viene registrata: chi, quando, su quale perimetro.
- Le operazioni privilegiate (entrare nelle network namespace) restano confinate nel demone **privsep**, dietro funzioni dichiarate con input validati (target IP, namespace `ovnmeta-<uuid>`); il server che riceve le richieste è non privilegiato ([0007](docs/adr/0007-privilegi-oslo-privsep.md)). Onestamente: su DevStack l'utente `stack` ha `sudo NOPASSWD:ALL`, quindi privsep **riduce** la superficie d'attacco ma **non è un confine di sicurezza rigido**; rootwrap è stato valutato e non adottato.

## Cosa non fa

Non entra nelle VM e non installa agenti. Non modifica risorse OpenStack: non crea VM, porte né regole di firewall. Non cerca vulnerabilità né tenta di sfruttarle: rileva servizi e versioni.

---

## Architettura

```mermaid
flowchart LR
    U[Utente o admin] -- "token Keystone" --> A[recon-api :5238]
    A --> D[(MySQL)]
    A -- "solo lettura" --> N[Nova e Neutron]
    A -- "nmap via privsep" --> R[Reti del progetto]
```

Componenti, confini e sequenza di una scansione: [docs/architettura.md](docs/architettura.md).

---

## Provarlo

### Installazione (plugin DevStack)

Nel `local.conf` di DevStack:

```ini
[[local|localrc]]
enable_plugin recon-stack https://github.com/suonatorefelice/recon-stack main
```

Un `local.conf` completo, con le impostazioni per una VM su Mac con chip Apple M1, è in [devstack/local.conf.sample](devstack/local.conf.sample).

Dopo `./stack.sh`, il servizio deve essere attivo e il servizio `recon` deve comparire nel catalogo Keystone:

```console
$ curl http://localhost:5238/health
{"status":"ok"}
$ sudo systemctl status devstack@recon-api
$ openstack catalog list        # compare il servizio recon-stack, tipo recon
```

### La demo

La demo guidata (preparazione del nodo, creazione del progetto `recon-demo`,
scansione dalla dashboard, le 7 segnalazioni attese e il report) è descritta in
un solo posto: **[docs/demo.md](docs/demo.md)**.

Il client del servizio è la **dashboard Horizon**; la API REST è disponibile
anche con `curl` e un token admin.

### Scansione periodica

Oltre alle scansioni avviate dalla dashboard, il server può scansionare da sé,
a intervalli regolari, i progetti indicati nel file
`/etc/recon-stack/recon-stack.conf`, sezione `[scanner]`:

```ini
periodic_scan_interval = 3600        # ogni ora
periodic_projects = recon-demo
```

Il confronto fra una scansione e la precedente (host e servizi comparsi o
spariti) si vede nel dettaglio della scansione, nella dashboard; avviando o
fermando un servizio su una VM demo, il diff lo mostra.

> **Nota di sviluppo.** Con `flask --app recon_stack.api.app:create_app run` (sviluppo locale, sul Mac) la API gira
> senza `keystonemiddleware`: il token non viene validato da Keystone e il
> contesto d'identità si legge dalle intestazioni della richiesta così come
> arrivano. È una modalità solo locale, per sviluppare: in produzione (uwsgi
> sul nodo DevStack) il token è sempre validato da Keystone.

## Sviluppo e test

Il servizio usa **MySQL** (ADR 0001), quindi sia l'esecuzione sia i test
unitari hanno bisogno di un server MySQL raggiungibile. Il DevStack ne ha già
uno acceso, perciò sviluppo e prove si fanno lì (o su qualsiasi macchina con
MySQL installato):

```console
$ python3 -m venv .venv
$ .venv/bin/pip install -e . -r test-requirements.txt tox

# Un database MySQL dedicato ai test (una volta sola):
$ mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS recon_stack_test;"

# L'indirizzo del database di test: utente/password/host del proprio MySQL.
$ export RECON_TEST_DATABASE_CONNECTION="mysql+pymysql://root:PASSWORD@127.0.0.1/recon_stack_test"
$ .venv/bin/tox -e py3                                            # test unitari
```

Senza la variabile `RECON_TEST_DATABASE_CONNECTION`, i test usano il valore
predefinito `mysql+pymysql://root@127.0.0.1/recon_stack_test`. Per una prova
rapida senza MySQL si può indicare un file SQLite
(`sqlite:////tmp/recon-test.sqlite`): passano tutti i test tranne quello sul
vincolo di chiave esterna, che SQLite non applica. Il percorso
completo su un DevStack vero si prova invece con i test tempest in
[recon_stack/tests/tempest](recon_stack/tests/tempest/README.md).

---

## Documenti

| Documento | Contenuto |
| --- | --- |
| [Concetti](docs/concetti.md) | OpenStack, DevStack, plugin, nmap e namespace di rete spiegati da zero |
| [Demo](docs/demo.md) | come preparare ed eseguire la demo dal vivo, e cosa crea il bersaglio (le 7 segnalazioni) |
| [Glossario](GLOSSARY.md) | i termini del dominio e dei componenti OpenStack |
| [Architettura](docs/architettura.md) | componenti, confini, sequenza di una scansione, dati conservati |
| [Decisioni](docs/adr/README.md) | le scelte di forma, con alternative scartate e fonti |
