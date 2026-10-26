# 0001 – Database: MySQL con SQLAlchemy, schema unico

## Contesto

Il servizio deve memorizzare lo stato delle scansioni, i risultati, lo storico e il log di chi ha avviato cosa. Il server scrive su questo database (anche da più thread). Non vogliamo riscrivere il codice se in futuro servirà un database diverso.

## Decisione

Usiamo **MySQL** come database e SQLAlchemy come ORM. Lo schema è definito dalle classi di `db/models.py` e si crea con `create_all` (comando `recon-stack-dbsync`). Non usiamo migrazioni: per un progetto didattico, con un solo schema e nessun dato da conservare fra versioni, basta ricreare il database quando i modelli cambiano. Il driver Python è **PyMySQL** (puro Python, lo stesso usato dai servizi OpenStack). La stringa di connessione sta nel file di configurazione del servizio (opzione `[database] connection`), nella forma `mysql+pymysql://utente:password@host/recon_stack`.

DevStack ha già un server MySQL acceso per gli altri componenti (Nova, Neutron, Keystone…): il plugin ci crea dentro un database dedicato con `recreate_database` e ne ricava l'indirizzo con `database_connection_url`, senza scrivere utente e password a mano.

MySQL gestisce più scrittori insieme, quindi i thread del server scrivono senza accorgimenti particolari, e InnoDB controlla le chiavi esterne (un host non può puntare a una scansione inesistente). Il codice resta quasi indipendente dal database: le sole attenzioni specifiche sono `pool_pre_ping`, che verifica che una connessione rimasta a lungo inattiva sia ancora viva prima di riusarla, e le date con i microsecondi (`DATETIME(6)`), perché due scansioni ravvicinate non abbiano lo stesso `created_at`.

## Alternative scartate

* **SQLite**: è un solo file, facile da ispezionare, copiare e azzerare, e per un progetto didattico basterebbe. Lo scartiamo perché i suoi tipi di dato sono più permissivi e nasconderebbero errori che MySQL segnala, e perché MySQL è il backend naturale di un servizio OpenStack: usarlo anche in sviluppo e nei test fa provare il codice sullo stesso database della realtà.
* **File JSON senza database**: non gestisce la concorrenza, e ci costringerebbe a riscrivere tutto dopo.
* **Migrazioni con Alembic**: sono lo strumento giusto quando uno schema in produzione deve evolvere senza perdere dati. Qui non c'è nulla da conservare, e aggiungerebbero file e passaggi senza beneficio.

## Conseguenze accettate

* Serve un server MySQL raggiungibile dovunque giri il servizio, DevStack compreso (lì è acceso per impostazione predefinita), e il driver PyMySQL tra le dipendenze.
* Anche i **test unitari** girano su MySQL: la fixture condivisa `clean_database` punta a un database di test (variabile d'ambiente `RECON_TEST_DATABASE_CONNECTION`) e, prima di ogni test, elimina le tabelle e ricrea lo schema dai modelli. Su DevStack MySQL c'è già; senza MySQL i test che usano il database non possono girare.
* I modelli sono lo schema: le colonne di testo hanno una lunghezza esplicita (es. `String(36)`), come MySQL richiede quando sono indicizzate.

## Fonti

* MySQL InnoDB e chiavi esterne: https://dev.mysql.com/doc/refman/8.0/en/innodb-foreign-key-constraints.html
* PyMySQL: https://pymysql.readthedocs.io/
* SQLAlchemy `create_all`: https://docs.sqlalchemy.org/en/20/core/metadata.html
