# 0010 – Dashboard come plugin di Horizon

## Contesto

OpenStack ha già una dashboard web ufficiale, **Horizon**, basata su Django: è il posto in cui gli amministratori accedono con le proprie credenziali Keystone e si aspettano di trovare le informazioni sul cloud. Horizon è progettato per essere esteso con *plugin*: un pacchetto esterno può aggiungere pannelli nuovi senza modificare Horizon, dichiarandoli con dei file "enabled".

Servire pagine HTML proprie da `recon-api` significherebbe invece: una seconda interfaccia web con un proprio login, un proprio aspetto, una propria gestione della sessione e del token, accanto a quella che l'amministratore usa già. Due posti dove guardare, due stili, due autenticazioni.

## Decisione

* L'interfaccia web di Recon-Stack è un **plugin di Horizon**: pannelli Django aggiunti alla dashboard esistente, non pagine servite da `recon-api`.
* I pannelli **non leggono il database**: chiamano la nostra API REST `/v1` (ADR [0008](0008-servizio-stile-openstack.md)) come qualsiasi altro client. Horizon ha già la sessione autenticata dell'utente, quindi passano il suo **token Keystone**: valgono le stesse regole di accesso della API (solo admin, ADR [0002](0002-autenticazione-keystone.md)). L'unica altra lettura è l'elenco dei progetti per il menu "Avvia scansione", che il modulo chiede a Keystone con le funzioni di Horizon.
* `recon-api` resta **solo API REST**: non serve HTML, non ha template.
* L'installazione del plugin la fa il plugin DevStack ([0009](0009-plugin-devstack.md)): copia i file "enabled" nella cartella di Horizon e riavvia la dashboard.

## Alternative scartate

* **Pagine Jinja2 servite da `recon-api`**: funzionerebbero, ma creano una seconda interfaccia web con login e aspetto propri, separata da dove l'amministratore già lavora. Più codice (login, sessione, stile) per un risultato meno integrato.
* **Applicazione a sé (single-page app) che chiama l'API**: massima libertà sull'aspetto, ma di nuovo un'interfaccia separata da gestire, servire e proteggere; sproporzionata per un progetto didattico.

## Conseguenze accettate

* Serve **Horizon attivo** sul nodo DevStack (lo è nelle installazioni predefinite) e una dipendenza dal framework della dashboard (Django/Horizon) per il codice dei pannelli.
* Il plugin DevStack deve installare i file "enabled" in Horizon e riavviarlo, oltre ad avviare `recon-api`.
* I pannelli dipendono dalla API `/v1`: se cambia il formato delle risposte, vanno aggiornati. In cambio la logica sta in un posto solo (l'API) e la dashboard non duplica l'accesso ai dati.
* L'aspetto e la navigazione sono quelli di Horizon: meno libertà grafica, ma piena coerenza con il resto della dashboard.

## Fonti

* Horizon plugin architecture: https://docs.openstack.org/horizon/latest/contributor/tutorials/plugin.html
* File "enabled" dei pannelli: https://docs.openstack.org/horizon/latest/contributor/topics/settings.html
* DevStack e Horizon: https://docs.openstack.org/devstack/latest/
