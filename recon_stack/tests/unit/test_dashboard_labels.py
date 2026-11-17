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
    for v in ("PENDING", "RUNNING", "DONE", "FAILED"):
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


def test_phase_label_e_testo_con_posizione():
    assert labels.phase_label("discovery") == "Scoperta host e servizi"
    assert labels.phase_text("discovery") == "Scoperta host e servizi (3 di 6)"
    # L'inventario è il primo passo, il perimetro il secondo (usa i floating IP).
    assert labels.phase_text("inventory").endswith("(1 di 6)")
    assert labels.phase_text("perimeter").endswith("(2 di 6)")
    assert labels.phase_text("exposure").endswith("(6 di 6)")


def test_phase_text_robusto():
    assert labels.phase_text(None) == ""
    assert labels.phase_text("boh") == ""          # non in SCAN_PHASES: niente posizione
    assert labels.phase_label("boh") == "boh"      # fallback al grezzo


def test_human_datetime_accorcia_la_data_iso():
    assert labels.human_datetime("2026-11-16T14:32:00.123456") == "2026-11-16 14:32"
    assert labels.human_datetime(None) == "—"
    assert labels.human_datetime("") == "—"
    # Un valore che non è una data ISO resta com'è (nessun errore).
    assert labels.human_datetime("mai") == "mai"


def test_nessun_import_db_nella_dashboard():
    # La dashboard gira dentro Horizon, dove SQLAlchemy non c'è: le costanti
    # devono venire da recon_stack.vocab, non da recon_stack.db.models.
    import pathlib
    import subprocess
    import sys

    # 1) labels e summary (puri, importabili sul Mac) in un processo pulito:
    #    né recon_stack.db né sqlalchemy devono finire in sys.modules.
    codice = (
        "import sys\n"
        "import recon_stack.dashboard.recon.labels\n"
        "import recon_stack.dashboard.recon.overview.summary\n"
        "assert 'recon_stack.db' not in sys.modules, 'db importato'\n"
        "assert 'sqlalchemy' not in sys.modules, 'sqlalchemy importato'\n"
    )
    r = subprocess.run([sys.executable, "-c", codice],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    # 2) Le viste importano Horizon (assente sul Mac): controllo statico che
    #    nessun file della dashboard nomini recon_stack.db.
    import recon_stack.dashboard as pkg
    for sorgente in pathlib.Path(pkg.__file__).parent.rglob("*.py"):
        assert "recon_stack.db" not in sorgente.read_text(), sorgente
