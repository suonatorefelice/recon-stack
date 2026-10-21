# 0002 – Autenticazione: token Keystone validati via keystonemiddleware

## Contesto

Il servizio deve accettare richieste solo da utenti autenticati, e un vincolo del progetto impone che le scansioni le avvii solo un amministratore. Non vogliamo gestire password, utenti e ruoli: sarebbe un secondo sistema di identità parallelo a quello del cloud, con rischi di sicurezza e di manutenzione.

## Decisione

Deleghiamo l'autenticazione a Keystone. Il servizio si aspetta l'header `X-Auth-Token`; il middleware keystonemiddleware valida il token contattando Keystone e arricchisce la richiesta con utente, progetto e ruoli. La cache dei token è abilitata per ridurre il carico su Keystone.

Regole di accesso:

* **avviare una scansione** richiede il ruolo `admin`; senza si risponde `403`, e il tentativo rifiutato viene registrato nel log;
* **leggere il catalogo**: un utente vede solo i dati del progetto del proprio token, un admin vede tutti i progetti;
* il log registra utente e progetto presi dal token validato, mai da campi scritti dal client.

## Alternative scartate

* **Utenti e password propri del servizio**: creerebbe un'isola di identità separata, con credenziali duplicate e nessuna integrazione con i ruoli OpenStack.
* **Validare i token a mano in ogni endpoint**: duplicherebbe logica e aumenterebbe il rischio di errori di sicurezza.

## Conseguenze accettate

* Dipendiamo da Keystone per l'autenticazione (mitigato dalla cache di keystonemiddleware).
* Il middleware ha bisogno di un utente di servizio in Keystone per verificare i token: lo crea il plugin DevStack ([0009](0009-plugin-devstack.md)).
* I test unitari useranno un sostituto del middleware che simula utente e ruoli; il percorso con Keystone vero si prova su DevStack.

## Fonti

* keystonemiddleware: https://docs.openstack.org/keystonemiddleware/latest/
