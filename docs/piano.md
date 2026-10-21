# Piano di lavoro

Il progetto procede per step. Uno step è chiuso solo quando la sua **verifica** passa; poi si fa il commit e si passa al successivo. Ogni commit cita la issue [#1](https://github.com/suonatorefelice/recon-stack/issues/1).

| Step | Contenuto | Verifica |
| --- | --- | --- |
| 1 | **Documentazione iniziale**: glossario, concetti, ADR, architettura, piano, README | i documenti sono coerenti fra loro e con CLAUDE.md |
| 2 | **Scheletro del servizio e plugin DevStack**: pacchetto `recon_stack`, `setup.cfg`, configurazione, app Flask con `/health`, `devstack/settings` e `plugin.sh` con tutte le fasi | Flask lanciato a mano risponde; con `stack.sh` i servizi `devstack@recon-api` e `devstack@recon-scanner` sono attivi e `curl http://<host>:5238/health` risponde; il servizio `recon` compare in `openstack catalog list` |
| 3 | **Database**: modelli SQLAlchemy, prima migrazione Alembic, comando `recon-stack-dbsync` | test unitari su SQLite in memoria; su DevStack le tabelle esistono dopo `stack.sh` |
| 4 | **Inventario** da Nova e Neutron, più `demo/setup_demo.sh` che crea un progetto di prova | l'inventario salvato coincide con `openstack server list`, `port list` e `floating ip list` sul progetto demo |
| 5 | **Autenticazione e vincoli**: keystonemiddleware, ruolo admin per le scansioni, calcolo e controllo del perimetro, limite di frequenza, log | test unitari: un IP fuori perimetro, un IP di un altro progetto e un utente non admin vengono rifiutati, e ogni tentativo finisce nel log |
| 6 | **Privsep e host discovery**: funzione privilegiata dichiarata con oslo.privsep, classificazione degli host | sul progetto demo le VM risultano censite e una porta creata senza VM risulta sconosciuta |
| 7 | **Service discovery** con `nmap -sV` | sulle VM demo vengono trovati i servizi e le versioni attese |
| 8 | **API REST** `/v1/hosts`, `/v1/services`, `/v1/scans`, più i comandi `openstack recon ...` | test con il client di test di Flask e con `curl` su DevStack |
| 9 | **Dashboard** con Jinja2: elenco host, dettaglio, servizi con filtri, storico | le ricerche dalla dashboard danno gli stessi risultati della API |
| 10 | **Scansione periodica, diff e storico** | avviando e fermando un servizio su una VM demo, il diff mostra la comparsa e la scomparsa |
| 11 | **Esposizione**: vista esterna dei floating IP, confronto con i security group (servizi latenti, regole inutili) | le regole volutamente sbagliate del progetto demo vengono segnalate |
| 12 | **Mappa e report**: topologia con Graphviz, report HTML/PDF, versione con redaction | il report del progetto demo è completo; la versione con redaction non contiene IP né identificativi reali |
| 13 | **Test**: suite unitaria con `tox -e py3`, plugin tempest per il percorso completo | `tox -e py3` passa senza OpenStack; i test tempest passano su DevStack |
| 14 | **Documentazione finale**: README completo, diagrammi, istruzioni d'uso | da un DevStack appena installato si arriva al report seguendo solo il README |

## Ambiente

- Sviluppo: il codice si scrive sul Mac e si prova a mano lanciando Flask; i test unitari girano senza OpenStack.
- Verifica: su una VM Linux con DevStack, dove il plugin si installa con `stack.sh`. `unstack.sh` e `stack.sh` si usano solo per verificare il plugin, non a ogni modifica.
- Le scansioni si eseguono solo sul progetto demo creato da `demo/setup_demo.sh`, in laboratorio.
