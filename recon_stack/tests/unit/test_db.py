# Test del database: migrazioni, impostazioni di SQLite e operazioni.
#
# Ogni test usa un file SQLite nuovo in una cartella temporanea. Non usiamo un
# database "in memoria" perché la modalità WAL esiste solo per i file, e
# vogliamo provare le stesse impostazioni usate in DevStack.

import pytest
import sqlalchemy
from alembic import autogenerate
from alembic import migration as alembic_migration

from recon_stack import conf
from recon_stack.cmd import dbsync
from recon_stack.db import api
from recon_stack.db import migration
from recon_stack.db import models


@pytest.fixture
def db(tmp_path):
    """Database nuovo, con tutte le migrazioni applicate."""
    conf.load([])
    conf.CONF.set_override(
        "connection", f"sqlite:///{tmp_path / 'test.sqlite'}", group="database")
    api.reset()
    migration.upgrade()
    yield
    api.reset()


# --- Migrazioni e impostazioni ----------------------------------------------

def test_le_migrazioni_creano_le_tabelle(db):
    tables = sqlalchemy.inspect(api.get_engine()).get_table_names()
    assert {"scans", "hosts", "services", "alembic_version"} <= set(tables)
    assert migration.current_revision() == "0001"


def test_modelli_e_migrazioni_descrivono_lo_stesso_schema(db):
    # Alembic confronta le classi di models.py con il database creato dalle
    # migrazioni. Se qualcuno cambia una classe senza scrivere la migrazione
    # (o viceversa), l'elenco delle differenze non è vuoto e il test fallisce.
    with api.get_engine().connect() as connection:
        context = alembic_migration.MigrationContext.configure(connection)
        differences = autogenerate.compare_metadata(context, models.Base.metadata)
    assert differences == []


def test_sqlite_usa_wal_e_controlla_le_chiavi_esterne(db):
    with api.get_engine().connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1


def test_dbsync_si_puo_ripetere(db):
    # Il database è già aggiornato dalla fixture: rilanciare il comando non
    # deve dare errori né cambiare la revisione.
    dbsync.main([])
    assert migration.current_revision() == "0001"


# --- Operazioni sulle scansioni ---------------------------------------------

def test_creare_e_rileggere_una_scansione(db):
    scan = api.create_scan("progetto-1", models.TRIGGER_MANUAL,
                           requested_by_user="admin-1",
                           requested_by_project="progetto-admin")
    saved = api.get_scan(scan.id)
    assert saved.project_id == "progetto-1"
    assert saved.status == models.SCAN_PENDING
    assert saved.requested_by_user == "admin-1"
    assert saved.created_at is not None


def test_un_tentativo_rifiutato_resta_nel_log(db):
    scan = api.create_scan("progetto-1", models.TRIGGER_MANUAL,
                           requested_by_user="utente-normale",
                           status=models.SCAN_REJECTED,
                           fault="ruolo admin richiesto")
    saved = api.get_scan(scan.id)
    assert saved.status == models.SCAN_REJECTED
    assert saved.fault == "ruolo admin richiesto"


def test_elenco_filtrato_per_progetto_e_stato(db):
    api.create_scan("progetto-1", models.TRIGGER_MANUAL)
    api.create_scan("progetto-2", models.TRIGGER_PERIODIC)
    api.create_scan("progetto-1", models.TRIGGER_MANUAL, status=models.SCAN_REJECTED)

    assert len(api.list_scans()) == 3
    assert len(api.list_scans(project_id="progetto-1")) == 2
    assert len(api.list_scans(project_id="progetto-1",
                              status=models.SCAN_PENDING)) == 1


def test_valori_sconosciuti_vengono_rifiutati(db):
    with pytest.raises(ValueError):
        api.create_scan("progetto-1", "a-caso")
    with pytest.raises(ValueError):
        api.create_scan("progetto-1", models.TRIGGER_MANUAL, status="QUASI")


def test_scansione_inesistente(db):
    assert api.get_scan("non-esiste") is None


def test_un_host_deve_appartenere_a_una_scansione_esistente(db):
    # Grazie a PRAGMA foreign_keys=ON, SQLite rifiuta un host che punta a una
    # scansione che non c'è.
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        with api.session_scope() as session:
            session.add(models.Host(scan_id="non-esiste", ip_address="10.0.0.5",
                                    classification=models.HOST_UNKNOWN))
