# 0004 – Scheduler in un processo separato dal server web

## Contesto

Le scansioni durano a lungo e vanno eseguite periodicamente. Se lo scheduler girasse dentro Flask o dentro un worker uwsgi, con più processi web si avrebbero più scheduler concorrenti che scansionano gli stessi bersagli, sprecando risorse e producendo risultati duplicati.

## Decisione

Separiamo due processi:

1. **Web/API** (Flask + uwsgi): riceve le richieste e legge il database; scrive solo le richieste di scansione e il log dei tentativi.
2. **Scheduler**: processo indipendente con APScheduler, esegue le scansioni periodiche e quelle richieste, e scrive i risultati nel database.

Entrambi sono servizi gestiti da DevStack (`run_process`), quindi servizi systemd `devstack@...`.

## Alternative scartate

* **Scheduler nel processo web**: con più worker si moltiplicherebbero le scansioni; con un solo worker l'API si bloccherebbe durante le scansioni.
* **Cron di sistema**: funzionerebbe, ma renderebbe più difficile condividere configurazione e logging con il resto del servizio.

## Conseguenze accettate

* Due processi da avviare e monitorare.
* La comunicazione avviene solo tramite database: la API scrive una richiesta, lo scheduler la trova al controllo successivo. Fra la richiesta e l'inizio della scansione passano quindi alcuni secondi.
* Se lo scheduler è fermo, le richieste restano in attesa, visibili come tali.

## Fonti

* Flask production deployment: https://flask.palletsprojects.com/en/stable/deploying/
* APScheduler: https://apscheduler.readthedocs.io/
