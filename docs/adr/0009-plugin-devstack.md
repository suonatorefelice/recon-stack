# 0009 – Plugin DevStack per l'integrazione

## Contesto

Dobbiamo integrare il servizio in DevStack in modo che venga installato, configurato e avviato insieme agli altri componenti. DevStack supporta plugin esterni tramite un contratto ben definito.

## Decisione

Creiamo un plugin DevStack chiamato `recon-stack`, con la struttura standard:

* `devstack/settings`: dichiara il plugin con `define_plugin recon-stack` e abilita i servizi `recon-api` e `recon-scanner`.
* `devstack/plugin.sh`: implementa le fasi chiamate da DevStack:
  * `stack install`: installa il pacchetto e le dipendenze di sistema (nmap, graphviz);
  * `stack post-config`: scrive la configurazione, crea il database, crea l'utente di servizio e registra servizio ed endpoint nel catalogo di Keystone, che a questo punto è già avviato;
  * `stack extra`: avvia `recon-api` e `recon-scanner`;
  * `unstack`: ferma i processi;
  * `clean`: rimuove configurazione e dati.

Il plugin si abilita in `local.conf` con:

```ini
enable_plugin recon-stack https://github.com/suonatorefelice/recon-stack main
```

## Alternative scartate

* **Script manuale di setup**: non si integra con il ciclo di vita di DevStack e va eseguito a mano ogni volta.
* **Modificare direttamente DevStack**: non sostenibile, le modifiche andrebbero perse a ogni aggiornamento.

## Conseguenze accettate

* Il plugin è codice bash da mantenere.
* Va rispettato il contratto di DevStack (fasi, variabili) per evitare rotture con aggiornamenti futuri.
* Il plugin può essere riusato in CI per test automatici.

## Fonti

* DevStack plugins: https://docs.openstack.org/devstack/latest/plugins.html
* Plugin registry: https://docs.openstack.org/devstack/latest/plugin-registry.html
