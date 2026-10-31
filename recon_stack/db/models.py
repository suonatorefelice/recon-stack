# Le tabelle del database come classi SQLAlchemy: ogni classe è una tabella,
# ogni attributo una colonna (ADR 0001). Queste classi sono lo schema: le
# tabelle le crea db/api.py con create_all (comando recon-stack-dbsync).

import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Le costanti di stato, fase, tipo e gravità stanno in vocab.py, che la
# dashboard importa senza SQLAlchemy. Le esponiamo anche qui perché il codice
# lato database le usi insieme ai modelli (models.SCAN_DONE accanto a models.Scan).
from recon_stack.vocab import (  # noqa: F401
    FINDING_EXTERNAL_ONLY, FINDING_EXTERNALLY_REACHABLE, FINDING_LATENT_SERVICE,
    FINDING_NO_PORT_SECURITY, FINDING_OVEREXPOSED, FINDING_UNKNOWN_EXPOSED,
    FINDING_USELESS_RULE, FINDING_WASTED_FLOATING_IP,
    PHASE_DISCOVERY, PHASE_EXPOSURE, PHASE_EXTERNAL, PHASE_INVENTORY,
    PHASE_PERIMETER, PHASE_SAVING, SCAN_DONE, SCAN_FAILED, SCAN_PENDING,
    SCAN_PHASES, SCAN_RUNNING, SCAN_STATUSES, SEVERITY_HIGH, SEVERITY_INFO,
    SEVERITY_LOW, SEVERITY_MEDIUM, SEVERITY_ORDER, TRIGGER_MANUAL,
    TRIGGER_PERIODIC,
)

# MySQL senza precisione tronca i DATETIME al secondo: usiamo DATETIME(6) coi
# microsecondi, così due scansioni ravvicinate non hanno lo stesso created_at
# (serve a get_previous_scan, che confronta con created_at <).
TIMESTAMP = DateTime().with_variant(MySQLDateTime(fsp=6), "mysql")


def utcnow():
    """Ora attuale in UTC, senza fuso: così è uguale su ogni macchina."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def new_id():
    """Nuovo identificativo univoco (UUID come stringa, come in OpenStack)."""
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Classe madre di tutte le tabelle."""


# Classificazione di un host (GLOSSARY.md).
HOST_KNOWN = "known"      # risponde e ha una porta Neutron
HOST_UNKNOWN = "unknown"  # risponde ma nessuna porta Neutron
HOST_ABSENT = "absent"    # ha una porta Neutron ma non risponde

# Da dove è stato visto un servizio.
VIEW_INTERNAL = "internal"  # dalla rete del progetto
VIEW_EXTERNAL = "external"  # sui floating IP

# Direzione in ingresso di una regola di security group (come la chiama Neutron):
# l'esposizione guarda solo le regole in ingresso.
DIRECTION_INGRESS = "ingress"


class Scan(Base):
    """Una scansione di un progetto; è anche la riga di log (ogni scansione
    avviata produce una riga: chi ha chiesto cosa, quando, su che perimetro)."""

    __tablename__ = "scans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    trigger: Mapped[str] = mapped_column(String(16))
    # Chi l'ha chiesta (dal token validato, ADR 0002); vuoti per le periodiche.
    requested_by_user: Mapped[str | None] = mapped_column(String(64))
    requested_by_project: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default=SCAN_PENDING, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, default=utcnow)
    started_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP)
    finished_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP)
    # Perimetro usato (subnet e floating IP), come testo JSON (ADR 0005).
    perimeter: Mapped[str | None] = mapped_column(Text)
    # Motivo del fallimento, leggibile da una persona.
    fault: Mapped[str | None] = mapped_column(Text)
    # Fase corrente (PHASE_*), solo per l'avanzamento; nulla a scansione finita.
    phase: Mapped[str | None] = mapped_column(String(32))

    hosts: Mapped[list["Host"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan")
    findings: Mapped[list["ExposureFinding"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan")


class Host(Base):
    """Un indirizzo IP del perimetro, come l'ha visto una scansione."""

    __tablename__ = "hosts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id"), index=True)
    # Testo (non un tipo indirizzo): IPv4 e IPv6 nella stessa colonna.
    ip_address: Mapped[str] = mapped_column(String(45), index=True)
    network_id: Mapped[str | None] = mapped_column(String(36))
    subnet_id: Mapped[str | None] = mapped_column(String(36))
    # Porta Neutron con questo IP, se c'è: è ciò che rende l'host "censito".
    neutron_port_id: Mapped[str | None] = mapped_column(String(36))
    # VM a cui appartiene la porta (le porte di router e DHCP non ne hanno).
    server_id: Mapped[str | None] = mapped_column(String(36))
    server_name: Mapped[str | None] = mapped_column(String(255))
    classification: Mapped[str] = mapped_column(String(16))

    scan: Mapped[Scan] = relationship(back_populates="hosts")
    services: Mapped[list["Service"]] = relationship(
        back_populates="host", cascade="all, delete-orphan")


class Service(Base):
    """Un programma in ascolto su una porta di un host."""

    __tablename__ = "services"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    host_id: Mapped[str] = mapped_column(ForeignKey("hosts.id"), index=True)
    # "port_number", non "port", per non confonderlo con la porta Neutron.
    port_number: Mapped[int]
    protocol: Mapped[str] = mapped_column(String(8))        # tcp o udp
    name: Mapped[str | None] = mapped_column(String(64), index=True)  # es. ssh
    product: Mapped[str | None] = mapped_column(String(255))          # es. OpenSSH
    version: Mapped[str | None] = mapped_column(String(255))          # es. 8.9p1
    view: Mapped[str] = mapped_column(String(16))

    host: Mapped[Host] = relationship(back_populates="services")


class ExposureFinding(Base):
    """Una segnalazione di esposizione, dal confronto servizi/security
    group. `message` è la spiegazione in italiano, letta così com'è da API
    e dashboard; gli altri campi servono a raggruppare e ordinare."""

    __tablename__ = "exposure_findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id"), index=True)
    finding_type: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))
    # Indirizzo a cui si riferisce (IP host o floating IP); porta/protocollo
    # solo per le segnalazioni legate a una porta.
    ip_address: Mapped[str | None] = mapped_column(String(45), index=True)
    port_number: Mapped[int | None]
    protocol: Mapped[str | None] = mapped_column(String(8))
    message: Mapped[str] = mapped_column(Text)

    scan: Mapped[Scan] = relationship(back_populates="findings")
