# Test della logica del pannello Riepilogo (dashboard/recon/overview/summary.py).
#
# La vista Django del pannello si verifica su DevStack; qui proviamo la sola
# funzione pura build_summary, che aggrega i dati dell'ultima scansione usando
# un client finto (niente Horizon). Verifica anche il "degrado con grazia": se
# la API non risponde, la pagina deve mostrare uno stato vuoto, non un errore.

from recon_stack.dashboard.recon.overview import summary


class _Client:
    def __init__(self, scans=None, findings=None, boom=False):
        self._scans, self._findings, self._boom = scans or [], findings or [], boom

    def list_scans(self, status=None):
        if self._boom:
            raise RuntimeError("api giù")
        return self._scans

    def get_scan_exposure(self, scan_id, severity=None):
        return self._findings


def test_nessuna_scansione_stato_vuoto():
    s = summary.build_summary(_Client(scans=[]))
    assert s["scan"] is None
    assert s["error"] is False
    assert sum(s["counts"].values()) == 0


def test_api_giu_non_rompe():
    s = summary.build_summary(_Client(boom=True))
    assert s["error"] is True
    assert s["scan"] is None


def test_conta_per_gravita_e_limita_le_piu_gravi():
    scans = [{"id": "s1", "status": "DONE"}]
    findings = [{"severity": "high"}, {"severity": "high"}, {"severity": "low"}]
    s = summary.build_summary(_Client(scans=scans, findings=findings), top=2)
    assert s["scan"]["id"] == "s1"
    assert s["counts"]["high"] == 2 and s["counts"]["low"] == 1
    assert s["counts"]["info"] == 0        # le gravità assenti restano a zero
    assert len(s["top_findings"]) == 2
