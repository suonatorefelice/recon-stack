# Test del modulo etichette della dashboard (dashboard/recon/labels.py).
#
# labels.py raccoglie in un posto solo le traduzioni italiane e i colori usati
# dai pannelli Horizon. Sono funzioni pure, senza import di Horizon/Django, così
# si possono provare sul Mac (dove Horizon non è installato).

from recon_stack.dashboard.recon import labels


def test_etichette_gravita_e_colori():
    assert labels.severity_label("high") == "Grave"
    assert labels.severity_css("high") == "danger"


def test_valore_sconosciuto_ripiega_sul_grezzo():
    assert labels.severity_label("xyz") == "xyz"
    assert labels.finding_label("boh") == "boh"
    assert labels.status_label("WAT") == "WAT"
    assert labels.severity_css("xyz") == "default"   # nessuna classe inventata


def test_tutti_i_valori_noti_sono_mappati():
    for v in ("high", "medium", "low", "info"):
        assert labels.severity_label(v) and labels.severity_css(v)
    for v in ("PENDING", "RUNNING", "DONE", "FAILED", "REJECTED"):
        assert labels.status_label(v) != v
    for v in ("manual", "periodic"):
        assert labels.trigger_label(v) != v
    for v in ("useless_rule", "latent_service", "overexposed",
              "externally_reachable", "unknown_exposed", "wasted_floating_ip",
              "external_only", "no_port_security"):
        assert labels.finding_label(v) != v


def test_short_uuid_robusto():
    assert labels.short_uuid(None) == "—"
    assert labels.short_uuid("") == "—"
    assert labels.short_uuid("abcd") == "abcd"
    assert labels.short_uuid("0123456789abcdef") == "01234567…"


def test_human_datetime_accorcia_la_data_iso():
    assert labels.human_datetime("2026-11-16T14:32:00.123456") == "2026-11-16 14:32"
    assert labels.human_datetime(None) == "—"
    assert labels.human_datetime("") == "—"
    # Un valore che non è una data ISO resta com'è (nessun errore).
    assert labels.human_datetime("mai") == "mai"
