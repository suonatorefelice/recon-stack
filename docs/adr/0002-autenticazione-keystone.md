# 0002 – Autenticazione: token Keystone validati via keystonemiddleware

## Contesto

Il servizio deve accettare richieste solo da utenti autenticati, e un vincolo del progetto impone che le scansioni le avvii solo un amministratore. Non vogliamo gestire password, utenti e ruoli: sarebbe un secondo sistema di identità parallelo a quello del cloud, con rischi di sicurezza e di manutenzione.

## Decisione

Deleghiamo l'autenticazione a Keystone. Il servizio si aspetta l'header `X-Auth-Token`; il middleware keystonemiddleware valida il token contattando Keystone e arricchisce la richiesta con utente, progetto e ruoli. La cache dei token è abilitata per ridurre il carico su Keystone.

Regole di accesso:

* **tutto `/v1` è riservato agli admin.** Un unico hook `before_request` sul blueprint `/v1` autorizza ogni rotta prima che venga eseguita: costruisce il contesto dal token validato e richiede il ruolo `admin`; senza token si risponde `401`, con token ma senza ruolo `403`. Non c'è un controllo per-progetto: Recon-Stack è uno strumento per l'operatore, non un RBAC OpenStack completo. Un solo punto di controllo vuol dire che una rotta nuova nasce già protetta, senza dover ricordare di ripetere la verifica;
* **`/health` resta pubblico**: è fuori dal blueprint `/v1`, non passa dall'hook, e con `delay_auth_decision` il middleware lo lascia rispondere anche senza token;
* **i rifiuti non toccano il database.** Una richiesta `401`/`403` la ferma l'hook *prima* di qualunque scrittura: resta solo nel log del servizio (motivo, e utente se noto). Il database contiene quindi solo scansioni vere;
* il log registra utente e progetto presi dal token validato, mai da campi scritti dal client.

Il **limite di frequenza** (una scansione troppo ravvicinata risponde `429`) è protetto da un `threading.Lock` di modulo attorno a "leggi l'ultima scansione del progetto, poi creane una nuova". Funziona perché c'è un solo processo (uwsgi `processes=1`, [ADR 0013](0013-server-unico.md)): con più processi servirebbe un lock nel database. Anche il `429` resta solo nel log, non scrive nel database.

## Alternative scartate

* **Utenti e password propri del servizio**: creerebbe un'isola di identità separata, con credenziali duplicate e nessuna integrazione con i ruoli OpenStack.
* **Validare i token a mano in ogni endpoint**: duplicherebbe logica e aumenterebbe il rischio di errori di sicurezza.

## Conseguenze accettate

* Dipendiamo da Keystone per l'autenticazione (mitigato dalla cache di keystonemiddleware).
* Il middleware ha bisogno di un utente di servizio in Keystone per verificare i token: lo crea il plugin DevStack ([0009](0009-plugin-devstack.md)).
* I test unitari useranno un sostituto del middleware che simula utente e ruoli; il percorso con Keystone vero si prova su DevStack.

## Fonti

* keystonemiddleware: https://docs.openstack.org/keystonemiddleware/latest/
