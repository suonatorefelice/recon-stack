# Test delle regole d'avvio di una scansione e del log (api/scans.py).
#
# Qui si verifica il cuore dello Step 5: un utente non admin e una richiesta
# troppo frequente vengono rifiutati, e ogni tentativo (accettato o rifiutato)
# lascia una riga nella tabella scans, che è il log.

import pytest

from recon_stack import conf
from recon_stack.api import context
from recon_stack.api import scans
from recon_stack.db import api
from recon_stack.db import migration
from recon_stack.db import models


@pytest.fixture
def db(tmp_path):
    conf.load([])
    conf.CONF.set_override(
        "connection", f"sqlite:///{tmp_path / 'test.sqlite'}", group="database")
    api.reset()
    migration.upgrade()
    yield
    api.reset()


def _ctx(roles="admin", authenticated=True):
    return context.RequestContext(
        authenticated=authenticated, user_id="user-1",
        project_id="progetto-admin", roles=tuple(roles.split(",")) if roles else ())


def test_admin_puo_avviare_e_la_scansione_e_registrata(db):
    scan = scans.request_scan(_ctx("admin"), "progetto-1")
    assert scan.status == models.SCAN_PENDING
    assert scan.requested_by_user == "user-1"
    # Registrata nel log.
    assert len(api.list_scans(project_id="progetto-1")) == 1


def test_utente_non_admin_rifiutato_ma_registrato(db):
    with pytest.raises(context.NotAuthorized):
        scans.request_scan(_ctx("member"), "progetto-1")
    # Il tentativo rifiutato è comunque nel log, con il motivo.
    logged = api.list_scans(project_id="progetto-1")
    assert len(logged) == 1
    assert logged[0].status == models.SCAN_REJECTED
    assert "admin" in logged[0].fault


def test_senza_token_rifiutato_ma_registrato(db):
    with pytest.raises(context.NotAuthenticated):
        scans.request_scan(_ctx(roles="", authenticated=False), "progetto-1")
    logged = api.list_scans(project_id="progetto-1")
    assert len(logged) == 1
    assert logged[0].status == models.SCAN_REJECTED


def test_richiesta_troppo_frequente_rifiutata_ma_registrata(db):
    conf.CONF.set_override("min_scan_interval", 3600, group="scanner")
    # Prima scansione: accettata.
    scans.request_scan(_ctx("admin"), "progetto-1")
    # Seconda subito dopo: rifiutata per frequenza.
    with pytest.raises(scans.RateLimited):
        scans.request_scan(_ctx("admin"), "progetto-1")

    logged = api.list_scans(project_id="progetto-1")
    assert len(logged) == 2
    assert logged[0].status == models.SCAN_REJECTED   # la più recente
    assert "frequente" in logged[0].fault
    assert logged[1].status == models.SCAN_PENDING    # la prima, accettata


def test_il_limite_di_frequenza_vale_per_progetto(db):
    conf.CONF.set_override("min_scan_interval", 3600, group="scanner")
    scans.request_scan(_ctx("admin"), "progetto-1")
    # Un altro progetto non è toccato dal limite del primo.
    other = scans.request_scan(_ctx("admin"), "progetto-2")
    assert other.status == models.SCAN_PENDING


def test_limite_disattivato_permette_scansioni_consecutive(db):
    conf.CONF.set_override("min_scan_interval", 0, group="scanner")
    scans.request_scan(_ctx("admin"), "progetto-1")
    second = scans.request_scan(_ctx("admin"), "progetto-1")
    assert second.status == models.SCAN_PENDING


def test_una_scansione_rifiutata_non_fa_da_limite(db):
    conf.CONF.set_override("min_scan_interval", 3600, group="scanner")
    # Un non admin genera solo righe REJECTED: non devono bloccare un admin.
    with pytest.raises(context.NotAuthorized):
        scans.request_scan(_ctx("member"), "progetto-1")
    scan = scans.request_scan(_ctx("admin"), "progetto-1")
    assert scan.status == models.SCAN_PENDING
