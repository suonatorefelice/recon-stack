# Test dell'esecuzione in-thread della scansione manuale (scanner/runner.py).
# I thread vengono attesi con join(); run_scan e la connessione sono sostituiti
# da finti, così non serve OpenStack.

import types

import pytest

from recon_stack import conf
from recon_stack.db import api as db
from recon_stack.db import models
from recon_stack.scanner import runner


@pytest.fixture
def database(clean_database):
    yield


def test_start_scan_esegue_run_scan_nel_thread(database, monkeypatch):
    scan = db.create_scan("p-1", models.TRIGGER_MANUAL, status=models.SCAN_PENDING)
    visti = []
    monkeypatch.setattr(runner.scan_mod, "run_scan",
                        lambda conn, sid: visti.append((conn, sid)))
    sentinella = object()
    runner.start_scan(scan.id, connect=lambda: sentinella).join()
    assert visti == [(sentinella, scan.id)]


def test_errore_in_run_scan_segna_failed_una_volta(database, monkeypatch):
    # run_scan vero: la connessione riesce ma il perimetro esplode. run_scan
    # segna già FAILED e rilancia; _esegui non deve riscrivere FAILED.
    scan = db.create_scan("p-1", models.TRIGGER_MANUAL, status=models.SCAN_PENDING)

    def perimetro_rotto(conn, project_id, floating_ips):
        raise RuntimeError("perimetro rotto")

    monkeypatch.setattr(runner.scan_mod.perimeter_mod, "build", perimetro_rotto)
    # L'inventario precede il perimetro: qui non è oggetto del test.
    monkeypatch.setattr(runner.scan_mod.inventory, "collect",
                        lambda conn, project_id, scan_id: ([], [], [], []))
    originale = db.update_scan
    scritture_failed = []

    def spia(scan_id, **campi):
        if campi.get("status") == models.SCAN_FAILED:
            scritture_failed.append(campi)
        return originale(scan_id, **campi)

    monkeypatch.setattr(db, "update_scan", spia)
    # Il progetto esiste (run_scan lo verifica per primo): la conn finta lo trova.
    conn = types.SimpleNamespace(identity=types.SimpleNamespace(
        find_project=lambda project_id, ignore_missing=True: object()))
    runner.start_scan(scan.id, connect=lambda: conn).join()
    assert len(scritture_failed) == 1
    aggiornata = db.get_scan(scan.id)
    assert aggiornata.status == models.SCAN_FAILED
    assert "perimetro rotto" in aggiornata.fault


def test_connessione_fallita_segna_failed(database, monkeypatch):
    # La connessione fallisce: run_scan non viene raggiunto, FAILED lo scrive _esegui.
    scan = db.create_scan("p-1", models.TRIGGER_MANUAL, status=models.SCAN_PENDING)
    chiamato = []
    monkeypatch.setattr(runner.scan_mod, "run_scan",
                        lambda conn, sid: chiamato.append(sid))

    def no_conn():
        raise RuntimeError("keystone irraggiungibile")

    runner.start_scan(scan.id, connect=no_conn).join()
    assert chiamato == []
    aggiornata = db.get_scan(scan.id)
    assert aggiornata.status == models.SCAN_FAILED
    assert aggiornata.fault == "keystone irraggiungibile"


# --- scansioni periodiche ----------------------------------------------------

class _Identity:
    def find_project(self, name_or_id, ignore_missing=True):
        if name_or_id == "recon-demo":
            return types.SimpleNamespace(id="progetto-1", name="recon-demo")
        return None


class _Conn:
    identity = _Identity()


def test_lo_scheduler_aggiunge_le_periodiche_solo_con_progetti():
    conf.load([])
    conf.CONF.set_override("periodic_scan_interval", 30, group="scanner")
    conf.CONF.set_override("periodic_projects", [], group="scanner")
    assert runner.build_scheduler().get_job("periodic_scans") is None
    conf.CONF.set_override("periodic_projects", ["recon-demo"], group="scanner")
    job = runner.build_scheduler().get_job("periodic_scans")
    assert job is not None and job.max_instances == 1


def test_lo_scheduler_senza_intervallo_non_ha_job():
    conf.load([])
    conf.CONF.set_override("periodic_scan_interval", 0, group="scanner")
    conf.CONF.set_override("periodic_projects", ["recon-demo"], group="scanner")
    assert runner.build_scheduler().get_jobs() == []


def test_run_periodic_esegue_una_scansione_per_progetto(database, monkeypatch):
    conf.load([])
    conf.CONF.set_override("periodic_projects", ["recon-demo"], group="scanner")
    eseguite = []
    monkeypatch.setattr(runner.scan_mod, "run_scan",
                        lambda conn, sid: eseguite.append(sid))
    runner.run_periodic_scans(connect=lambda: _Conn())
    scans = db.list_scans(project_id="progetto-1")
    assert len(scans) == 1 and scans[0].trigger == models.TRIGGER_PERIODIC
    assert eseguite == [scans[0].id]


def test_run_periodic_un_errore_non_ferma_gli_altri(database, monkeypatch):
    conf.load([])
    conf.CONF.set_override("periodic_projects", ["x", "recon-demo"],
                           group="scanner")

    class Identity:
        def find_project(self, name_or_id, ignore_missing=True):
            if name_or_id == "x":
                raise RuntimeError("keystone giu")
            return types.SimpleNamespace(id="progetto-1")

    conn = types.SimpleNamespace(identity=Identity())
    eseguite = []
    monkeypatch.setattr(runner.scan_mod, "run_scan",
                        lambda c, sid: eseguite.append(sid))
    runner.run_periodic_scans(connect=lambda: conn)
    assert len(eseguite) == 1


def test_run_periodic_progetto_sconosciuto_saltato(database, monkeypatch):
    conf.load([])
    conf.CONF.set_override("periodic_projects", ["boh"], group="scanner")
    monkeypatch.setattr(runner.scan_mod, "run_scan", lambda c, s: None)
    runner.run_periodic_scans(connect=lambda: _Conn())
    assert db.list_scans() == []


def test_start_scheduler_non_ne_avvia_due(monkeypatch):
    conf.load([])
    monkeypatch.setattr(runner, "_scheduler", None)
    s1 = runner.start_scheduler()
    try:
        assert runner.start_scheduler() is s1
    finally:
        s1.shutdown(wait=False)


def test_fail_orphan_scans_chiude_le_running(database):
    viva = db.create_scan("p-1", models.TRIGGER_MANUAL, status=models.SCAN_RUNNING)
    fatta = db.create_scan("p-1", models.TRIGGER_MANUAL, status=models.SCAN_DONE)
    assert runner.fail_orphan_scans() == 1
    assert db.get_scan(viva.id).status == models.SCAN_FAILED
    assert "riavvio" in db.get_scan(viva.id).fault
    assert db.get_scan(fatta.id).status == models.SCAN_DONE
