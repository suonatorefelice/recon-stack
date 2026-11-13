# Test delle regole d'avvio di una scansione e del log (api/v1.py).
#
# Il ruolo admin è controllato a monte (hook di /v1, vedi test_v1). Qui si
# verifica il limite di frequenza: una richiesta troppo ravvicinata solleva
# RateLimited e non scrive nulla; solo le scansioni accettate sono righe.

import types

import pytest
import werkzeug.exceptions

from recon_stack import conf
from recon_stack.api import context
from recon_stack.api import v1
from recon_stack.db import api
from recon_stack.db import models


@pytest.fixture
def db(clean_database):
    # clean_database (in conftest.py) prepara un database MySQL di test pulito.
    yield


def _ctx(roles="admin", authenticated=True):
    return context.RequestContext(
        authenticated=authenticated, user_id="user-1",
        project_id="progetto-admin", roles=tuple(roles.split(",")) if roles else ())


class _FakeIdentity:
    def __init__(self, progetti):
        self._progetti = progetti  # {nome_o_id: id canonico}

    def find_project(self, name_or_id, ignore_missing=False):
        canonico = self._progetti.get(name_or_id)
        if canonico is None:
            return None
        return types.SimpleNamespace(id=canonico)


def _connect(progetti=None):
    """Connessione OpenStack finta: risolve nome o id a id canonico.

    Senza argomenti ogni stringa è già un id canonico (identità)."""
    class _Conn:
        identity = (_FakeIdentity(progetti) if progetti is not None
                    else types.SimpleNamespace(
                        find_project=lambda x, ignore_missing=False:
                        types.SimpleNamespace(id=x)))
    return lambda: _Conn()


def test_admin_puo_avviare_e_la_scansione_e_registrata(db):
    scan = v1.request_scan(_ctx("admin"), "progetto-1", connect=_connect())
    assert scan.status == models.SCAN_PENDING
    assert scan.requested_by_user == "user-1"
    # Registrata nel log.
    assert len(api.list_scans(project_id="progetto-1")) == 1


def test_richiesta_troppo_frequente_solleva_e_non_registra(db):
    conf.CONF.set_override("min_scan_interval", 3600, group="scanner")
    # Prima scansione: accettata.
    v1.request_scan(_ctx("admin"), "progetto-1", connect=_connect())
    # Seconda subito dopo: rifiutata per frequenza.
    with pytest.raises(v1.RateLimited):
        v1.request_scan(_ctx("admin"), "progetto-1", connect=_connect())

    # Il rifiuto non scrive nulla: resta la sola scansione PENDING.
    logged = api.list_scans(project_id="progetto-1")
    assert len(logged) == 1
    assert logged[0].status == models.SCAN_PENDING


def test_il_limite_di_frequenza_vale_per_progetto(db):
    conf.CONF.set_override("min_scan_interval", 3600, group="scanner")
    v1.request_scan(_ctx("admin"), "progetto-1", connect=_connect())
    # Un altro progetto non è toccato dal limite del primo.
    other = v1.request_scan(_ctx("admin"), "progetto-2", connect=_connect())
    assert other.status == models.SCAN_PENDING


def test_limite_disattivato_permette_scansioni_consecutive(db):
    conf.CONF.set_override("min_scan_interval", 0, group="scanner")
    v1.request_scan(_ctx("admin"), "progetto-1", connect=_connect())
    second = v1.request_scan(_ctx("admin"), "progetto-1", connect=_connect())
    assert second.status == models.SCAN_PENDING


def test_request_scan_risolve_il_nome_in_id(db):
    connect = _connect({"recon-demo": "ID123"})
    scan = v1.request_scan(_ctx("admin"), "recon-demo", connect=connect)
    assert scan.project_id == "ID123"
    assert len(api.list_scans(project_id="ID123")) == 1
    assert api.list_scans(project_id="recon-demo") == []


def test_request_scan_progetto_inesistente_404(db):
    with pytest.raises(werkzeug.exceptions.NotFound):
        v1.request_scan(_ctx("admin"), "non-esiste",
                        connect=_connect({"altro": "ID9"}))
    # Nessuna riga scansione creata.
    assert api.list_scans() == []


def test_rate_limit_non_si_aggira_con_nome_e_id(db):
    conf.CONF.set_override("min_scan_interval", 3600, group="scanner")
    connect = _connect({"recon-demo": "ID123", "ID123": "ID123"})
    v1.request_scan(_ctx("admin"), "ID123", connect=connect)
    with pytest.raises(v1.RateLimited):
        v1.request_scan(_ctx("admin"), "recon-demo", connect=connect)
    assert len(api.list_scans(project_id="ID123")) == 1
