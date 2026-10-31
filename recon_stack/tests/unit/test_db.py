# Test del database: schema e operazioni.
#
# I test girano su MySQL come il servizio vero (ADR 0001): la fixture condivisa
# clean_database (in conftest.py) prepara un database di test pulito, con lo
# schema creato dai modelli (db/api.py create_all).

import pytest
import sqlalchemy

from recon_stack.cmd import dbsync
from recon_stack.db import api
from recon_stack.db import models


@pytest.fixture
def db(clean_database):
    yield


# --- Schema -----------------------------------------------------------------

def test_lo_schema_crea_le_tabelle(db):
    tables = sqlalchemy.inspect(api.get_engine()).get_table_names()
    assert {"scans", "hosts", "services", "exposure_findings"} <= set(tables)


def test_dbsync_si_puo_ripetere(db):
    # Lo schema è già creato dalla fixture: rilanciare il comando (create_all)
    # non deve dare errori e le tabelle restano.
    dbsync.main([])
    tables = sqlalchemy.inspect(api.get_engine()).get_table_names()
    assert "scans" in tables


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


def test_una_scansione_fallita_conserva_il_motivo(db):
    scan = api.create_scan("progetto-1", models.TRIGGER_MANUAL,
                           requested_by_user="utente-normale",
                           status=models.SCAN_FAILED,
                           fault="ruolo admin richiesto")
    saved = api.get_scan(scan.id)
    assert saved.status == models.SCAN_FAILED
    assert saved.fault == "ruolo admin richiesto"


def test_elenco_filtrato_per_progetto_e_stato(db):
    api.create_scan("progetto-1", models.TRIGGER_MANUAL)
    api.create_scan("progetto-2", models.TRIGGER_PERIODIC)
    api.create_scan("progetto-1", models.TRIGGER_MANUAL, status=models.SCAN_FAILED)

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


def test_scan_phases_costanti_ordinate():
    # Le fasi in ordine di avanzamento: la loro lunghezza è il "di 6".
    assert models.SCAN_PHASES == (
        models.PHASE_INVENTORY, models.PHASE_PERIMETER, models.PHASE_DISCOVERY,
        models.PHASE_SAVING, models.PHASE_EXTERNAL, models.PHASE_EXPOSURE)
    assert len(models.SCAN_PHASES) == 6


def test_scan_salva_e_rilegge_la_fase(db):
    scan = api.create_scan("progetto-1", models.TRIGGER_MANUAL)
    api.update_scan(scan.id, phase=models.PHASE_DISCOVERY)
    assert api.get_scan(scan.id).phase == models.PHASE_DISCOVERY


def test_un_host_deve_appartenere_a_una_scansione_esistente(db):
    # MySQL (InnoDB) controlla le chiavi esterne da solo: rifiuta un host che
    # punta a una scansione che non c'è.
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        with api.session_scope() as session:
            session.add(models.Host(scan_id="non-esiste", ip_address="10.0.0.5",
                                    classification=models.HOST_UNKNOWN))
