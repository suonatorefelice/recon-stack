# Collegamento al database e operazioni di lettura e scrittura.
#
# Il resto del servizio non usa SQLAlchemy direttamente: chiama le funzioni di
# questo modulo (create_scan, get_scan, ...). Così il modo in cui i dati sono
# salvati resta in un posto solo, e i test possono provarlo da solo.
#
# Due processi usano lo stesso database (ADR 0001, ADR 0004): recon-api scrive
# le richieste e il log, recon-scanner i risultati. Per SQLite questo vuol dire
# due cose, impostate in _configure_sqlite:
#   - modalità WAL: chi legge non viene bloccato da chi sta scrivendo;
#   - busy_timeout: chi deve scrivere mentre un altro scrive aspetta qualche
#     istante invece di ricevere subito l'errore "database is locked".

import contextlib

import sqlalchemy
from sqlalchemy import orm

from recon_stack import conf
from recon_stack.db import models

# Il motore (engine) è l'oggetto che tiene le connessioni al database. Se ne
# crea uno solo per processo, la prima volta che serve: crearlo a ogni
# operazione sarebbe lento e aprirebbe connessioni inutili.
_engine = None
_session_factory = None


def _configure_sqlite(dbapi_connection, connection_record):
    """Impostazioni applicate a ogni nuova connessione SQLite.

    SQLAlchemy chiama questa funzione da solo (vedi event.listen in
    get_engine) ogni volta che apre una connessione.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute(f"PRAGMA busy_timeout={int(conf.CONF.database.busy_timeout)}")
    # SQLite, per compatibilità con le versioni vecchie, non controlla le
    # chiavi esterne se non glielo si chiede: senza questa riga si potrebbe
    # salvare un host che punta a una scansione inesistente.
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine():
    """Restituisce il motore del database, creandolo la prima volta."""
    global _engine
    if _engine is None:
        url = conf.CONF.database.connection
        _engine = sqlalchemy.create_engine(url)
        if _engine.dialect.name == "sqlite":
            sqlalchemy.event.listen(_engine, "connect", _configure_sqlite)
    return _engine


def reset():
    """Chiude il motore: la prossima operazione ne crea uno nuovo.

    Serve ai test, che cambiano database da un test all'altro.
    """
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


@contextlib.contextmanager
def session_scope():
    """Una "sessione" di lavoro sul database, da usare con "with".

        with session_scope() as session:
            session.add(...)

    Se il blocco finisce bene, le modifiche vengono salvate tutte insieme
    (commit); se c'è un errore, vengono annullate tutte (rollback). Così il
    database non resta mai con metà di un'operazione scritta.
    """
    global _session_factory
    if _session_factory is None:
        # expire_on_commit=False: gli oggetti restano leggibili anche dopo la
        # fine della sessione, così le funzioni possono restituirli.
        _session_factory = orm.sessionmaker(bind=get_engine(), expire_on_commit=False)
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# --- Scansioni ---------------------------------------------------------------

def create_scan(project_id, trigger, requested_by_user=None,
                requested_by_project=None, status=models.SCAN_PENDING,
                fault=None):
    """Registra una scansione e la restituisce.

    status e fault permettono di registrare subito un tentativo rifiutato
    (REJECTED, con il motivo): anche quelli devono finire nel log.
    """
    if trigger not in (models.TRIGGER_MANUAL, models.TRIGGER_PERIODIC):
        raise ValueError(f"trigger sconosciuto: {trigger}")
    if status not in models.SCAN_STATUSES:
        raise ValueError(f"stato sconosciuto: {status}")
    scan = models.Scan(
        project_id=project_id,
        trigger=trigger,
        requested_by_user=requested_by_user,
        requested_by_project=requested_by_project,
        status=status,
        fault=fault,
    )
    with session_scope() as session:
        session.add(scan)
    return scan


def get_scan(scan_id):
    """Restituisce la scansione con questo id, oppure None se non esiste."""
    with session_scope() as session:
        return session.get(models.Scan, scan_id)


def list_scans(project_id=None, status=None):
    """Elenco delle scansioni, dalla più recente, filtrabile per progetto e stato."""
    query = sqlalchemy.select(models.Scan).order_by(models.Scan.created_at.desc())
    if project_id is not None:
        query = query.where(models.Scan.project_id == project_id)
    if status is not None:
        query = query.where(models.Scan.status == status)
    with session_scope() as session:
        return list(session.scalars(query))
