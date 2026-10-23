# Le tabelle del database, descritte come classi Python (docs/architettura.md,
# sezione "Dati conservati").
#
# Con SQLAlchemy ogni classe corrisponde a una tabella e ogni attributo a una
# colonna: invece di scrivere SQL a mano si lavora con oggetti Python, e
# SQLAlchemy traduce nel dialetto del database in uso (SQLite oggi, MySQL se
# un giorno servisse, ADR 0001).
#
# ATTENZIONE: queste classi descrivono lo schema, ma non lo creano. Le tabelle
# le crea e le modifica alembic, con le migrazioni in migrations/versions/.
# Ogni modifica qui va accompagnata da una nuova migrazione; un test
# (test_db.py) controlla che le due cose siano allineate.
#
# Gli identificativi nel codice sono in inglese, come nel resto di OpenStack;
# il significato dei termini è nel glossario (GLOSSARY.md).

import datetime
import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow():
    """Ora attuale in UTC, senza fuso orario.

    Salviamo sempre in UTC: un orario "locale" cambia significato con l'ora
    legale e fra macchine diverse. SQLite non conserva il fuso orario, quindi
    lo togliamo esplicitamente invece di lasciarlo perdere in silenzio.
    """
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def new_id():
    """Nuovo identificativo univoco, nello stesso formato usato da OpenStack."""
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Classe madre di tutte le tabelle: SQLAlchemy raccoglie qui lo schema."""


# Stati di una scansione (docs/architettura.md, "Sequenza di una scansione").
SCAN_PENDING = "PENDING"    # richiesta registrata, lo scanner non l'ha ancora presa
SCAN_RUNNING = "RUNNING"    # in corso
SCAN_DONE = "DONE"          # completata
SCAN_FAILED = "FAILED"      # interrotta da un errore, motivo in "fault"
SCAN_REJECTED = "REJECTED"  # rifiutata prima di partire: ruolo, frequenza o perimetro
SCAN_STATUSES = (SCAN_PENDING, SCAN_RUNNING, SCAN_DONE, SCAN_FAILED, SCAN_REJECTED)

# Chi ha originato la scansione.
TRIGGER_MANUAL = "manual"      # chiesta da un admin con POST /v1/scans
TRIGGER_PERIODIC = "periodic"  # avviata dallo scheduler (step 10)

# Classificazione di un host (GLOSSARY.md).
HOST_KNOWN = "known"      # host censito: risponde e ha una porta Neutron
HOST_UNKNOWN = "unknown"  # host sconosciuto: risponde ma nessuna porta Neutron
HOST_ABSENT = "absent"    # host assente: ha una porta Neutron ma non risponde

# Da dove è stato visto un servizio (GLOSSARY.md).
VIEW_INTERNAL = "internal"  # vista interna, dalla rete del progetto
VIEW_EXTERNAL = "external"  # vista esterna, sui floating IP


class Scan(Base):
    """Una scansione di un progetto: è anche la riga di log richiesta dai vincoli.

    Ogni tentativo produce una riga, anche se rifiutato (stato REJECTED):
    così il log dice sempre chi ha chiesto cosa, quando e su quale perimetro.
    """

    __tablename__ = "scans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # Progetto scansionato (id Keystone).
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    trigger: Mapped[str] = mapped_column(String(16))
    # Chi l'ha chiesta: utente e progetto presi dal token validato (ADR 0002).
    # Vuoti per le scansioni periodiche, che le chiede il servizio stesso.
    requested_by_user: Mapped[str | None] = mapped_column(String(64))
    requested_by_project: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default=SCAN_PENDING, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(default=utcnow)
    started_at: Mapped[datetime.datetime | None]
    finished_at: Mapped[datetime.datetime | None]
    # Perimetro effettivo usato, scritto come testo JSON (ADR 0005): l'elenco
    # delle subnet e dei floating IP letti da Neutron all'inizio.
    perimeter: Mapped[str | None] = mapped_column(Text)
    # Motivo del fallimento o del rifiuto, leggibile da una persona.
    fault: Mapped[str | None] = mapped_column(Text)

    hosts: Mapped[list["Host"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan")


class Host(Base):
    """Un indirizzo IP del perimetro, come l'ha visto una scansione."""

    __tablename__ = "hosts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id"), index=True)
    # Testo, non un tipo "indirizzo": SQLite non ne ha uno, e così IPv4 e IPv6
    # stanno nella stessa colonna (45 caratteri bastano per un IPv6).
    ip_address: Mapped[str] = mapped_column(String(45), index=True)
    network_id: Mapped[str | None] = mapped_column(String(36))
    subnet_id: Mapped[str | None] = mapped_column(String(36))
    # Porta Neutron con questo IP, se c'è: è ciò che rende l'host "censito".
    neutron_port_id: Mapped[str | None] = mapped_column(String(36))
    # VM a cui appartiene la porta, se è una VM (le porte di router e DHCP no).
    server_id: Mapped[str | None] = mapped_column(String(36))
    server_name: Mapped[str | None] = mapped_column(String(255))
    classification: Mapped[str] = mapped_column(String(16))

    scan: Mapped[Scan] = relationship(back_populates="hosts")
    services: Mapped[list["Service"]] = relationship(
        back_populates="host", cascade="all, delete-orphan")


class Service(Base):
    """Un programma in ascolto su una porta di un host (GLOSSARY.md)."""

    __tablename__ = "services"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    host_id: Mapped[str] = mapped_column(ForeignKey("hosts.id"), index=True)
    # "port_number" e non "port", per non confonderlo con la porta Neutron
    # (GLOSSARY.md, "Conflitti di terminologia").
    port_number: Mapped[int]
    protocol: Mapped[str] = mapped_column(String(8))        # tcp o udp
    name: Mapped[str | None] = mapped_column(String(64), index=True)  # es. ssh
    product: Mapped[str | None] = mapped_column(String(255))          # es. OpenSSH
    version: Mapped[str | None] = mapped_column(String(255))          # es. 8.9p1
    view: Mapped[str] = mapped_column(String(16))

    host: Mapped[Host] = relationship(back_populates="services")
