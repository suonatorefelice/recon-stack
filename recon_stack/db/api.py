# Collegamento al database e operazioni di lettura/scrittura. Il resto del
# servizio non usa SQLAlchemy direttamente: chiama queste funzioni, così il
# "come" si salva sta in un posto solo. Scrive un solo processo (il server
# unico, ADR 0013) ma da più thread, le richieste e le scansioni in background:
# ogni operazione apre la propria sessione (session_scope), quindi i thread
# non condividono stato.

import contextlib

import sqlalchemy
from sqlalchemy import orm

from recon_stack import conf
from recon_stack.db import models

# Un solo motore (engine) per processo, creato alla prima necessità.
_engine = None
_session_factory = None


def get_engine():
    """Restituisce il motore del database, creandolo la prima volta."""
    global _engine
    if _engine is None:
        # pool_pre_ping: verifica che una connessione a lungo inattiva sia ancora
        # viva (MySQL le chiude) e, se non lo è, ne apre una nuova.
        _engine = sqlalchemy.create_engine(conf.CONF.database.connection,
                                           pool_pre_ping=True)
    return _engine


def create_all():
    """Crea le tabelle definite dai modelli (ADR 0001); quelle già presenti restano.

    Lo usa recon-stack-dbsync. Lo schema è definito solo dalle classi di
    models.py: se cambia, si modificano i modelli e si ricrea il database.
    """
    models.Base.metadata.create_all(get_engine())


def drop_all():
    """Elimina tutte le tabelle dei modelli. Serve ai test, per ripartire puliti."""
    models.Base.metadata.drop_all(get_engine())


def reset():
    """Chiude il motore; la prossima operazione ne crea uno nuovo. Serve ai test."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


@contextlib.contextmanager
def session_scope():
    """Una sessione di lavoro: commit se tutto va bene, rollback se c'è un errore.

    Garanzia di atomicità: il database non resta mai con mezza operazione scritta.
    """
    global _session_factory
    if _session_factory is None:
        # expire_on_commit=False: gli oggetti restano leggibili dopo il commit,
        # così le funzioni possono restituirli.
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


# Scansioni

def create_scan(project_id, trigger, requested_by_user=None,
                requested_by_project=None, status=models.SCAN_PENDING,
                fault=None):
    """Registra una scansione e la restituisce.

    Include chi l'ha chiesta e lo stato iniziale.
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
    """La scansione con questo id, o None."""
    with session_scope() as session:
        return session.get(models.Scan, scan_id)


def update_scan(scan_id, **fields):
    """Aggiorna alcuni campi di una scansione (stato, orari, perimetro, fault)."""
    with session_scope() as session:
        scan = session.get(models.Scan, scan_id)
        for name, value in fields.items():
            setattr(scan, name, value)
        return scan


def list_scans(project_id=None, status=None):
    """Elenco delle scansioni, dalla più recente, filtrabile per progetto e stato."""
    query = sqlalchemy.select(models.Scan).order_by(models.Scan.created_at.desc())
    if project_id is not None:
        query = query.where(models.Scan.project_id == project_id)
    if status is not None:
        query = query.where(models.Scan.status == status)
    with session_scope() as session:
        return list(session.scalars(query))


def get_previous_scan(project_id, before, status=models.SCAN_DONE):
    """La scansione completata del progetto subito prima di `before` (per il diff)."""
    query = (sqlalchemy.select(models.Scan)
             .where(models.Scan.project_id == project_id)
             .where(models.Scan.status == status)
             .where(models.Scan.created_at < before)
             .order_by(models.Scan.created_at.desc()))
    with session_scope() as session:
        return session.scalars(query).first()


def get_latest_scan(project_id=None, status=models.SCAN_DONE):
    """La scansione più recente, filtrata per progetto e stato (None = ogni stato).

    Con i valori predefiniti è l'ultima DONE: il "catalogo" dell'API.
    """
    query = sqlalchemy.select(models.Scan).order_by(models.Scan.created_at.desc())
    if project_id is not None:
        query = query.where(models.Scan.project_id == project_id)
    if status is not None:
        query = query.where(models.Scan.status == status)
    with session_scope() as session:
        return session.scalars(query.limit(1)).first()


# Host

def save_hosts(scan_id, hosts):
    """Salva gli host trovati e li restituisce (col loro id, per agganciarvi i servizi).

    hosts: lista di dizionari coi campi di models.Host (da discovery.classify).
    """
    objects = [models.Host(scan_id=scan_id, **host) for host in hosts]
    with session_scope() as session:
        session.add_all(objects)
    return objects


def get_hosts(scan_id, classification=None):
    """Elenco degli host di una scansione, filtrabile per classificazione."""
    query = sqlalchemy.select(models.Host).where(models.Host.scan_id == scan_id)
    if classification is not None:
        query = query.where(models.Host.classification == classification)
    with session_scope() as session:
        return list(session.scalars(query))


def get_host(host_id):
    """L'host con questo id, o None."""
    with session_scope() as session:
        return session.get(models.Host, host_id)


# Servizi

def save_services(services):
    """Salva i servizi trovati (lista di dizionari coi campi di models.Service)."""
    with session_scope() as session:
        session.add_all(
            models.Service(**service) for service in services)


def get_services(scan_id=None, host_id=None, name=None):
    """Elenco dei servizi, filtrabile per scansione, host e nome (i filtri si combinano)."""
    # selectinload carica anche l'host di ogni servizio nella stessa sessione,
    # così l'IP è leggibile dopo che la sessione è chiusa (API /v1/services).
    query = sqlalchemy.select(models.Service).options(
        orm.selectinload(models.Service.host))
    if scan_id is not None:
        query = (query
                 .join(models.Host, models.Service.host_id == models.Host.id)
                 .where(models.Host.scan_id == scan_id))
    if host_id is not None:
        query = query.where(models.Service.host_id == host_id)
    if name is not None:
        query = query.where(models.Service.name == name)
    with session_scope() as session:
        return list(session.scalars(query))


# Segnalazioni di esposizione

def save_findings(findings):
    """Salva le segnalazioni (lista di dizionari coi campi di models.ExposureFinding)."""
    with session_scope() as session:
        session.add_all(
            models.ExposureFinding(**finding) for finding in findings)


def get_findings(scan_id, severity=None):
    """Segnalazioni di una scansione, dalla più grave, filtrabili per gravità."""
    query = (sqlalchemy.select(models.ExposureFinding)
             .where(models.ExposureFinding.scan_id == scan_id))
    if severity is not None:
        query = query.where(models.ExposureFinding.severity == severity)
    with session_scope() as session:
        findings = list(session.scalars(query))
    # Ordine per gravità (SEVERITY_ORDER) e poi per indirizzo, in Python: così è
    # indipendente dall'ordine in cui il database restituirebbe le righe.
    findings.sort(key=lambda f: (models.SEVERITY_ORDER.get(f.severity, 99),
                                 f.ip_address or "", f.port_number or 0))
    return findings
