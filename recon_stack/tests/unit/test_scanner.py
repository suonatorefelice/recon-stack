# Test del processo recon-scanner (recon_stack/cmd/scanner.py).
#
# Non avviamo lo scheduler, che resterebbe acceso per sempre: controlliamo che
# venga costruito con i compiti giusti e proviamo i compiti (esecuzione delle
# PENDING, accodamento periodico) con una connessione finta.

import types

import pytest

from recon_stack import conf
from recon_stack.cmd import scanner
from recon_stack.db import api as db
from recon_stack.db import migration
from recon_stack.db import models


@pytest.fixture
def database(tmp_path):
    conf.load([])
    conf.CONF.set_override(
        "connection", f"sqlite:///{tmp_path / 'test.sqlite'}", group="database")
    db.reset()
    migration.upgrade()
    yield
    db.reset()


# --- build_scheduler ---------------------------------------------------------

def test_lo_scheduler_ha_il_battito_con_l_intervallo_configurato():
    conf.load([])
    conf.CONF.set_override("heartbeat_interval", 15, group="scanner")
    job = scanner.build_scheduler().get_job("heartbeat")
    assert job is not None
    assert job.trigger.interval.total_seconds() == 15
    assert job.max_instances == 1


def test_lo_scheduler_aggiunge_l_esecutore_se_il_poll_e_attivo():
    conf.load([])
    conf.CONF.set_override("scan_poll_interval", 10, group="scanner")
    assert scanner.build_scheduler().get_job("run_pending_scans") is not None


def test_lo_scheduler_non_aggiunge_l_esecutore_se_poll_zero():
    conf.load([])
    conf.CONF.set_override("scan_poll_interval", 0, group="scanner")
    assert scanner.build_scheduler().get_job("run_pending_scans") is None


def test_lo_scheduler_aggiunge_le_periodiche_solo_con_progetti():
    conf.load([])
    conf.CONF.set_override("periodic_scan_interval", 30, group="scanner")
    # Senza progetti configurati il compito non c'è.
    conf.CONF.set_override("periodic_projects", [], group="scanner")
    assert scanner.build_scheduler().get_job("enqueue_periodic_scans") is None
    # Con almeno un progetto, c'è.
    conf.CONF.set_override("periodic_projects", ["recon-demo"], group="scanner")
    assert scanner.build_scheduler().get_job("enqueue_periodic_scans") is not None


# --- run_pending_scans -------------------------------------------------------

def test_esegue_le_pending_dalla_piu_vecchia(database, monkeypatch):
    # Due scansioni in attesa: la prima creata va eseguita per prima.
    first = db.create_scan("p-1", models.TRIGGER_MANUAL, status=models.SCAN_PENDING)
    second = db.create_scan("p-1", models.TRIGGER_MANUAL, status=models.SCAN_PENDING)

    eseguite = []
    monkeypatch.setattr(scanner.scan_mod, "run_scan",
                        lambda conn, scan_id: eseguite.append(scan_id))
    scanner.run_pending_scans(connect=lambda: object())

    assert eseguite == [first.id, second.id]


def test_senza_pending_non_si_connette(database, monkeypatch):
    # Nessuna PENDING: connect non deve nemmeno essere chiamata.
    chiamate = []
    scanner.run_pending_scans(connect=lambda: chiamate.append(1))
    assert chiamate == []


def test_un_errore_su_una_scansione_non_ferma_le_altre(database, monkeypatch):
    a = db.create_scan("p-1", models.TRIGGER_MANUAL, status=models.SCAN_PENDING)
    b = db.create_scan("p-1", models.TRIGGER_MANUAL, status=models.SCAN_PENDING)

    eseguite = []

    def run(conn, scan_id):
        if scan_id == a.id:
            raise RuntimeError("boom")
        eseguite.append(scan_id)

    monkeypatch.setattr(scanner.scan_mod, "run_scan", run)
    scanner.run_pending_scans(connect=lambda: object())
    # La seconda è stata comunque eseguita.
    assert eseguite == [b.id]


# --- enqueue_periodic_scans --------------------------------------------------

class _Identity:
    def find_project(self, name_or_id, ignore_missing=True):
        if name_or_id == "recon-demo":
            return types.SimpleNamespace(id="progetto-1", name="recon-demo")
        return None


class _Conn:
    identity = _Identity()


def test_accoda_una_pending_per_ogni_progetto(database):
    conf.CONF.set_override("periodic_projects", ["recon-demo"], group="scanner")
    scanner.enqueue_periodic_scans(connect=lambda: _Conn())

    scans = db.list_scans(project_id="progetto-1")
    assert len(scans) == 1
    assert scans[0].status == models.SCAN_PENDING
    assert scans[0].trigger == models.TRIGGER_PERIODIC


def test_progetto_sconosciuto_viene_saltato(database):
    conf.CONF.set_override("periodic_projects", ["non-esiste"], group="scanner")
    scanner.enqueue_periodic_scans(connect=lambda: _Conn())
    assert db.list_scans() == []
