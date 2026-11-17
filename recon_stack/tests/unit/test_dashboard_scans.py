# Test della scelta dei progetti per il menu "Avvia scansione".
#
# Verifica la logica pura di recon_stack/dashboard/recon/scans/progetti.py:
# dal menu deve comparire solo il progetto scansionabile (recon-demo), senza i
# progetti di sistema di OpenStack. È logica senza Horizon né Django, quindi si
# prova direttamente sul Mac.

from recon_stack.dashboard.recon.scans import progetti


class _Progetto:
    """Finto progetto Keystone: ha un id e (di solito) un nome."""

    def __init__(self, id, name=None):
        self.id = id
        if name is not None:
            self.name = name


def test_tiene_solo_recon_demo_di_default():
    elenco = [_Progetto("1", "admin"),
              _Progetto("2", "recon-demo"),
              _Progetto("3", "service")]
    assert progetti.scelte_menu(elenco) == [("2", "recon-demo")]


def test_consentiti_personalizzati():
    elenco = [_Progetto("1", "admin"),
              _Progetto("2", "recon-demo"),
              _Progetto("3", "prova")]
    scelte = progetti.scelte_menu(elenco, ["recon-demo", "prova"])
    assert scelte == [("2", "recon-demo"), ("3", "prova")]


def test_ripiego_su_tutti_se_nessuno_combacia():
    # Nessun progetto si chiama recon-demo: meglio mostrarli tutti che un menu
    # vuoto che bloccherebbe l'avvio delle scansioni.
    elenco = [_Progetto("1", "admin"), _Progetto("3", "service")]
    assert progetti.scelte_menu(elenco) == [("1", "admin"), ("3", "service")]


def test_senza_nome_usa_id():
    # Un progetto senza attributo name: si usa l'id come etichetta. Non è fra i
    # consentiti di default, quindi si ricade nel ripiego "tutti".
    elenco = [_Progetto("abc")]
    assert progetti.scelte_menu(elenco) == [("abc", "abc")]


def test_elenco_vuoto():
    assert progetti.scelte_menu([]) == []
