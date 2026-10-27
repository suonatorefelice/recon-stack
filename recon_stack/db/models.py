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

# Direzione di una regola di security group (come la chiama Neutron).
DIRECTION_INGRESS = "ingress"  # traffico in entrata verso la VM
DIRECTION_EGRESS = "egress"    # traffico in uscita dalla VM

# Tipi di segnalazione di esposizione (step 11). Descrivono un'incongruenza fra
# i servizi davvero in ascolto e ciò che i security group permettono, oppure una
# situazione di rischio (host non censito, floating IP inutile).
FINDING_USELESS_RULE = "useless_rule"            # regola che apre una porta senza servizio
FINDING_LATENT_SERVICE = "latent_service"        # servizio attivo non previsto da regole
FINDING_OVEREXPOSED = "overexposed"              # servizio aperto a qualunque indirizzo
FINDING_EXTERNALLY_REACHABLE = "externally_reachable"  # confermato raggiungibile dal floating IP
FINDING_UNKNOWN_EXPOSED = "unknown_exposed"      # host non censito con porte aperte
FINDING_WASTED_FLOATING_IP = "wasted_floating_ip"  # floating IP senza servizi dietro
FINDING_EXTERNAL_ONLY = "external_only"          # visto da fuori ma non censito internamente

# Gravità di una segnalazione, dalla più alla meno urgente.
SEVERITY_HIGH = "high"      # rischio concreto: va guardato subito
SEVERITY_MEDIUM = "medium"  # da verificare
SEVERITY_LOW = "low"        # pulizia / igiene della configurazione
SEVERITY_INFO = "info"      # conferma, nessun problema in sé
# Ordine di gravità, per presentare prima le segnalazioni più urgenti.
SEVERITY_ORDER = {SEVERITY_HIGH: 0, SEVERITY_MEDIUM: 1,
                  SEVERITY_LOW: 2, SEVERITY_INFO: 3}


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
    # La "fotografia" dell'inventario letto da OpenStack all'inizio della
    # scansione (step 4): serve a classificare gli host e resta allegata alla
    # scansione, così ogni scansione sa su quali risorse si basava.
    servers: Mapped[list["InventoryServer"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan")
    ports: Mapped[list["InventoryPort"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan")
    floating_ips: Mapped[list["InventoryFloatingIp"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan")
    security_groups: Mapped[list["InventorySecurityGroup"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan")
    security_group_rules: Mapped[list["InventorySecurityGroupRule"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan")
    findings: Mapped[list["ExposureFinding"]] = relationship(
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


# --- Inventario: la fotografia delle risorse OpenStack (step 4) --------------
#
# Queste tabelle salvano ciò che il servizio ha letto da Nova e Neutron
# all'inizio di una scansione (ADR 0003: solo lettura, mai modifiche). Non
# sono la verità sulle risorse — quella resta OpenStack (ADR 0001) — ma la
# copia usata da quella scansione: così, anche a distanza di tempo, si sa quali
# VM, porte e floating IP c'erano quando la scansione è stata fatta.


class InventoryServer(Base):
    """Una VM (server Nova) del progetto, come letta all'inizio della scansione."""

    __tablename__ = "inventory_servers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id"), index=True)
    # id della VM in Nova (lo stesso che mostra "openstack server list").
    server_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    # Stato Nova: ACTIVE, SHUTOFF, ... Una VM spenta esiste ma non risponderà.
    status: Mapped[str | None] = mapped_column(String(32))

    scan: Mapped[Scan] = relationship(back_populates="servers")


class InventoryPort(Base):
    """Un indirizzo IP fisso di una porta Neutron del progetto.

    Una porta Neutron può avere più IP fissi: salviamo una riga per ogni IP,
    così la colonna ip_address contiene sempre un solo indirizzo ed è facile,
    più avanti (step 6), ritrovare la porta a partire da un IP visto nella rete.
    """

    __tablename__ = "inventory_ports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id"), index=True)
    port_id: Mapped[str] = mapped_column(String(36), index=True)
    network_id: Mapped[str | None] = mapped_column(String(36))
    subnet_id: Mapped[str | None] = mapped_column(String(36))
    ip_address: Mapped[str] = mapped_column(String(45), index=True)
    mac_address: Mapped[str | None] = mapped_column(String(32))
    # A cosa serve la porta: "compute:nova" è una VM, "network:router_interface"
    # un router, "network:dhcp" il DHCP. Serve a distinguere le porte delle VM
    # da quelle dell'infrastruttura di rete.
    device_owner: Mapped[str | None] = mapped_column(String(64))
    # Risorsa a cui la porta è attaccata: per una VM è l'id del server Nova.
    device_id: Mapped[str | None] = mapped_column(String(255))
    # I security group applicati a questa porta, come lista JSON di id (step 11):
    # servono a collegare una porta (e quindi un host) alle sue regole, per
    # confrontare i servizi trovati con ciò che le regole permettono. Testo JSON
    # perché una porta può avere più security group e SQLite non ha un tipo lista.
    security_group_ids: Mapped[str | None] = mapped_column(Text)

    scan: Mapped[Scan] = relationship(back_populates="ports")


class InventoryFloatingIp(Base):
    """Un floating IP del progetto e la porta interna a cui è associato."""

    __tablename__ = "inventory_floating_ips"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id"), index=True)
    floating_ip_id: Mapped[str] = mapped_column(String(36), index=True)
    # L'indirizzo pubblico (sulla rete esterna) e l'IP privato a cui inoltra.
    floating_ip_address: Mapped[str] = mapped_column(String(45), index=True)
    fixed_ip_address: Mapped[str | None] = mapped_column(String(45))
    # Porta Neutron a cui il floating IP è associato, se è associato.
    port_id: Mapped[str | None] = mapped_column(String(36))

    scan: Mapped[Scan] = relationship(back_populates="floating_ips")


class InventorySecurityGroup(Base):
    """Un security group del progetto, come letto all'inizio della scansione.

    Un security group è un gruppo di regole di firewall che Neutron applica alle
    porte (e quindi alle VM). Qui salviamo solo l'anagrafica del gruppo (id e
    nome); le singole regole stanno in InventorySecurityGroupRule.
    """

    __tablename__ = "inventory_security_groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id"), index=True)
    # id del security group in Neutron (lo stesso di "openstack security group list").
    security_group_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str | None] = mapped_column(String(255))

    scan: Mapped[Scan] = relationship(back_populates="security_groups")


class InventorySecurityGroupRule(Base):
    """Una regola di un security group: cosa lascia passare e da dove.

    Confrontando queste regole con i servizi davvero in ascolto (step 11) si
    trovano le incongruenze: una porta aperta da una regola ma senza servizio
    (regola inutile), un servizio attivo che nessuna regola prevede (servizio
    latente), una regola che apre una porta a qualunque indirizzo (esposizione
    eccessiva).
    """

    __tablename__ = "inventory_sg_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(36), index=True)
    # A quale security group appartiene la regola.
    security_group_id: Mapped[str] = mapped_column(String(36), index=True)
    direction: Mapped[str] = mapped_column(String(16))  # ingress o egress
    # Famiglia di indirizzi: IPv4 o IPv6.
    ethertype: Mapped[str | None] = mapped_column(String(16))
    # Protocollo (tcp, udp, icmp, ...). None vuol dire "qualunque protocollo".
    protocol: Mapped[str | None] = mapped_column(String(16))
    # Intervallo di porte permesse: da port_range_min a port_range_max inclusi.
    # Entrambi None vuol dire "tutte le porte" (tipico di una regola senza porta).
    port_range_min: Mapped[int | None]
    port_range_max: Mapped[int | None]
    # Da quali indirizzi è permesso il traffico: un CIDR (es. 0.0.0.0/0 = tutti)
    # oppure, in alternativa, un altro security group (remote_group_id).
    remote_ip_prefix: Mapped[str | None] = mapped_column(String(64))
    remote_group_id: Mapped[str | None] = mapped_column(String(36))

    scan: Mapped[Scan] = relationship(back_populates="security_group_rules")


class ExposureFinding(Base):
    """Una segnalazione di esposizione prodotta da una scansione (step 11).

    Nasce dal confronto fra i servizi trovati e i security group (scanner/
    exposure.py). Il campo message contiene la spiegazione in italiano, pensata
    per essere letta così com'è nella API, nel comando e nella dashboard; gli
    altri campi servono a raggruppare e ordinare. La salviamo nel database come
    gli altri risultati, così entra nello storico della scansione.
    """

    __tablename__ = "exposure_findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id"), index=True)
    finding_type: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))
    # Indirizzo a cui la segnalazione si riferisce: l'IP di un host o un floating
    # IP. Porta e protocollo ci sono solo per le segnalazioni legate a una porta.
    ip_address: Mapped[str | None] = mapped_column(String(45), index=True)
    port_number: Mapped[int | None]
    protocol: Mapped[str | None] = mapped_column(String(8))
    message: Mapped[str] = mapped_column(Text)

    scan: Mapped[Scan] = relationship(back_populates="findings")
