# Test del contesto della richiesta e del controllo del ruolo (api/context.py).

import pytest

from recon_stack.api import context


def _headers(status="Confirmed", roles="admin", **extra):
    h = {
        "X-Identity-Status": status,
        "X-User-Id": "user-1",
        "X-User-Name": "admin",
        "X-Project-Id": "progetto-admin",
        "X-Project-Name": "admin",
        "X-Roles": roles,
    }
    h.update(extra)
    return h


def test_legge_identita_e_ruoli():
    ctx = context.RequestContext.from_headers(_headers(roles="admin,member"))
    assert ctx.authenticated is True
    assert ctx.user_id == "user-1"
    assert ctx.project_id == "progetto-admin"
    assert ctx.roles == ("admin", "member")
    assert ctx.is_admin is True


def test_admin_passa():
    ctx = context.RequestContext.from_headers(_headers(roles="admin"))
    ctx.require_admin()  # non solleva niente


def test_utente_non_admin_viene_rifiutato():
    ctx = context.RequestContext.from_headers(_headers(roles="member,reader"))
    assert ctx.is_admin is False
    with pytest.raises(context.NotAuthorized):
        ctx.require_admin()


def test_senza_token_valido_viene_rifiutato():
    ctx = context.RequestContext.from_headers(_headers(status="Invalid"))
    assert ctx.authenticated is False
    with pytest.raises(context.NotAuthenticated):
        ctx.require_admin()


def test_intestazioni_assenti_danno_un_contesto_vuoto():
    ctx = context.RequestContext.from_headers({})
    assert ctx.authenticated is False
    assert ctx.roles == ()
    with pytest.raises(context.NotAuthenticated):
        ctx.require_admin()
