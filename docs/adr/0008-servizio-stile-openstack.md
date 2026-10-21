# 0008 – Servizio in stile OpenStack: Flask + uwsgi sulla porta 5238, registrato nel catalogo

## Contesto

Flask include un server di sviluppo, ma la documentazione ufficiale dice di non usarlo in produzione: non è progettato per essere efficiente, stabile e sicuro. Inoltre un componente OpenStack deve essere registrato nel catalogo di Keystone per essere trovato dagli altri componenti e dai client, ad esempio dalla riga di comando `openstack`.

## Decisione

* Usiamo **uwsgi** come application server per Flask, come fanno i componenti OpenStack installati da DevStack.
* uwsgi ascolta direttamente sulla **porta 5238**, richiesta dal progetto. La funzione di DevStack `write_uwsgi_config`, se le si passa una porta, fa ascoltare uwsgi su quella porta invece di metterlo dietro Apache.
* Registriamo il servizio nel catalogo di Keystone con un tipo dedicato (`recon`) e l'endpoint `http://<host>:5238`. La registrazione la fa il plugin DevStack in modo ripetibile ([0009](0009-plugin-devstack.md)).

## Alternative scartate

* **Server di sviluppo di Flask**: la documentazione lo esclude per la produzione, e non è gestito come gli altri servizi.
* **Dietro Apache su un percorso** (es. `/recon`), come fanno molti componenti DevStack: valido, ma il progetto richiede la porta 5238.
* **Gunicorn**: valido, ma uwsgi è quello che DevStack configura già, con funzioni pronte per i plugin.

## Conseguenze accettate

* Dobbiamo configurare e mantenere uwsgi: il file di configurazione lo genera il plugin, il processo lo gestisce DevStack come servizio systemd.
* La registrazione nel catalogo richiede privilegi amministrativi su Keystone, che il plugin ha durante l'installazione.
* Il servizio diventa individuabile dagli altri componenti OpenStack tramite il catalogo.

## Fonti

* Flask deployment: https://flask.palletsprojects.com/en/stable/deploying/
* uwsgi: https://uwsgi-docs.readthedocs.io/
* `write_uwsgi_config` in DevStack: https://opendev.org/openstack/devstack/src/branch/master/lib/apache
* Keystone service catalog: https://docs.openstack.org/keystone/latest/
