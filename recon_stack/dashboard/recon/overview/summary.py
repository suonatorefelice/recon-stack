# Logica del pannello Riepilogo: riassume l'ultima scansione completata. Funzione
# pura (niente Horizon/Django): prende un client /v1 e torna un dizionario pronto
# per il template, che i test provano con un client finto. Se la API non risponde
# torna uno stato vuoto con error=True (la pagina non salta).

from recon_stack import vocab
from recon_stack.dashboard.recon import labels


# Tutte le gravità, così i conteggi partono da zero e la riga dei badge mostra
# anche le gravità assenti (es. "Gravi: 0").
def _empty_counts():
    return {s: 0 for s in labels.SEVERITIES}


def build_summary(client, top=5):
    """Riassume l'ultima scansione DONE.

    Ritorna un dizionario con:
      - scan: l'ultima scansione completata (dict) o None se non ce ne sono;
      - counts: numero di segnalazioni per gravità (tutte e quattro, anche 0);
      - top_findings: le prime `top` segnalazioni più gravi;
      - error: True se una chiamata alla API è fallita.
    """
    try:
        done = client.list_scans(status=vocab.SCAN_DONE)
        scan = done[0] if done else None
        if scan is None:
            return {"scan": None, "counts": _empty_counts(),
                    "top_findings": [], "error": False}

        findings = client.get_scan_exposure(scan["id"])
        counts = _empty_counts()
        for f in findings:
            sev = f.get("severity")
            if sev in counts:
                counts[sev] += 1
        # Ordine per gravità (la API già le ordina così; lo imponiamo comunque,
        # per non dipendere dall'ordine di arrivo).
        ordered = sorted(
            findings,
            key=lambda f: vocab.SEVERITY_ORDER.get(f.get("severity"), 99))
        return {"scan": labels.enrich_scan(scan), "counts": counts,
                "top_findings": ordered[:top], "error": False}
    except Exception:
        return {"scan": None, "counts": _empty_counts(),
                "top_findings": [], "error": True}
