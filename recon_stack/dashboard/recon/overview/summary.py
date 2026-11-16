# La logica del pannello Riepilogo: riassume l'ultima scansione completata.
#
# È una funzione pura (nessun import di Horizon/Django): prende un client della
# API /v1 e restituisce un dizionario pronto da mostrare. La vista Django
# (views.py) la chiama e passa il risultato al template. Tenendo qui la logica,
# la possiamo provare sul Mac con un client finto.
#
# "Degrado con grazia": se la API non risponde, invece di far saltare la pagina
# restituiamo uno stato vuoto con error=True, e il template mostra un avviso.

from recon_stack.db import models
from recon_stack.dashboard.recon import labels


# Tutte le gravità, così i conteggi partono da zero e la riga dei badge mostra
# anche le gravità assenti (es. "Gravi: 0").
_SEVERITIES = ("high", "medium", "low", "info")


def _empty_counts():
    return {s: 0 for s in _SEVERITIES}


def _enrich_scan(scan):
    """Aggiunge alla scansione i campi già tradotti/leggibili per il template.

    Il Riepilogo è la pagina d'atterraggio: la scansione deve arrivare con le
    etichette italiane, gli UUID accorciati e le date in forma breve, così il
    template non mostra valori grezzi (la data ISO piena, un UUID lungo, ...).
    """
    scan = dict(scan)
    scan["status_it"] = labels.status_label(scan.get("status"))
    scan["trigger_it"] = labels.trigger_label(scan.get("trigger"))
    scan["id_short"] = labels.short_uuid(scan.get("id"))
    scan["project_short"] = labels.short_uuid(scan.get("project_id"))
    scan["created_h"] = labels.human_datetime(scan.get("created_at"))
    scan["started_h"] = labels.human_datetime(scan.get("started_at"))
    scan["finished_h"] = labels.human_datetime(scan.get("finished_at"))
    return scan


def build_summary(client, top=5):
    """Riassume l'ultima scansione DONE.

    Ritorna un dizionario con:
      - scan: l'ultima scansione completata (dict) o None se non ce ne sono;
      - counts: numero di segnalazioni per gravità (tutte e quattro, anche 0);
      - top_findings: le prime `top` segnalazioni più gravi;
      - error: True se una chiamata alla API è fallita.
    """
    try:
        done = client.list_scans(status=models.SCAN_DONE)
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
            key=lambda f: models.SEVERITY_ORDER.get(f.get("severity"), 99))
        return {"scan": _enrich_scan(scan), "counts": counts,
                "top_findings": ordered[:top], "error": False}
    except Exception:
        return {"scan": None, "counts": _empty_counts(),
                "top_findings": [], "error": True}
