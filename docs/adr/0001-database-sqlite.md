# 0001 – Database: SQLite con SQLAlchemy, migrazioni Alembic

## Contesto

Il servizio deve memorizzare lo stato delle scansioni, i risultati, lo storico e il log di chi ha avviato cosa. Non vogliamo riscrivere il codice se in futuro servirà un database diverso, e serve un meccanismo per far evolvere lo schema nel tempo.

## Decisione

Usiamo SQLite come database su DevStack, SQLAlchemy come ORM e Alembic per le migrazioni. La stringa di connessione sta nel file di configurazione del servizio (opzione `[database] connection`), così si può passare a MySQL senza toccare il codice.

SQLite viene aperto in modalità **WAL** (*write-ahead logging*): le letture non vengono bloccate da una scrittura in corso, e chi deve scrivere mentre un altro sta scrivendo aspetta qualche istante invece di ricevere subito un errore.

## Alternative scartate

* **MySQL da subito**: DevStack lo ha già installato e acceso per gli altri componenti, quindi non costerebbe infrastruttura in più. Lo scartiamo per ora perché SQLite è un solo file, facile da ispezionare, copiare e azzerare durante lo sviluppo, e i volumi di questo servizio sono piccoli. Resta la strada naturale se gli scrittori aumentano.
* **File JSON senza database**: non gestisce la concorrenza né le migrazioni, e ci costringerebbe a riscrivere tutto dopo.

## Conseguenze accettate

* Gli scrittori sono due: la API registra le richieste di scansione e il log dei tentativi, anche quelli rifiutati; lo scheduler ([0004](0004-scheduler-separato.md)) scrive i risultati. SQLite permette un solo scrittore alla volta: con WAL e un tempo di attesa le scritture della API, brevi e rare, si mettono in coda dietro a quelle dello scheduler.
* Le migrazioni Alembic vanno mantenute allineate al modello SQLAlchemy.
* Se il carico crescesse, andrà cambiato il backend in MySQL modificando solo la configurazione.

## Fonti

* SQLite locking: https://www.sqlite.org/lockingv3.html
* SQLite WAL: https://www.sqlite.org/wal.html
* Alembic: https://alembic.sqlalchemy.org/
