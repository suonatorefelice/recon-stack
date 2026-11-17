# Etichette italiane e colori per la dashboard: traduciamo qui, in un posto solo,
# i valori grezzi della API (high/DONE/overexposed, ...) e ne associamo il colore
# del badge. Funzioni pure (niente Horizon/Django), provate dai test unitari; ognuna
# ripiega sul valore grezzo se non lo conosce (.get(v, v)), così un tipo nuovo
# della API non rompe la pagina.

from recon_stack import vocab


# Le gravità dalla più alla meno urgente, nell'ordine di vocab.SEVERITY_ORDER:
# è l'ordine dei badge e dei conteggi in dashboard.
SEVERITIES = tuple(sorted(vocab.SEVERITY_ORDER, key=vocab.SEVERITY_ORDER.get))

# Gravità (vocab.SEVERITY_*): etichetta leggibile e classe colore del badge.
SEVERITY_LABELS = {
    "high": "Grave",
    "medium": "Media",
    "low": "Bassa",
    "info": "Informativa",
}

# Classi dei badge Bootstrap che Horizon già include (label label-<css>):
# danger=rosso, warning=arancio, info=azzurro, default=grigio.
SEVERITY_CSS = {
    "high": "danger",
    "medium": "warning",
    "low": "info",
    "info": "default",
}

# Tipi di segnalazione (vocab.FINDING_*): nome tecnico -> frase breve italiana.
FINDING_LABELS = {
    "overexposed": "Esposto a chiunque",
    "latent_service": "Servizio non previsto",
    "useless_rule": "Regola inutile",
    "unknown_exposed": "Host sconosciuto esposto",
    "externally_reachable": "Raggiungibile da fuori",
    "wasted_floating_ip": "Floating IP sprecato",
    "external_only": "Visto solo da fuori",
    "no_port_security": "Senza port security",
}

# Stato della scansione (vocab.SCAN_*).
STATUS_LABELS = {
    "PENDING": "In attesa",
    "RUNNING": "In corso",
    "DONE": "Completata",
    "FAILED": "Fallita",
}

# Origine della scansione (vocab.TRIGGER_*).
TRIGGER_LABELS = {
    "manual": "Manuale",
    "periodic": "Periodica",
}

# Fasi di una scansione in corso (vocab.PHASE_*): nome tecnico -> etichetta.
PHASE_LABELS = {
    "inventory": "Inventario",
    "perimeter": "Perimetro",
    "discovery": "Scoperta host e servizi",
    "saving": "Salvataggio",
    "external": "Vista esterna",
    "exposure": "Esposizione",
}

# Classificazione di un host (models.HOST_*): known/unknown/absent.
CLASSIFICATION_LABELS = {
    "known": "censito",
    "unknown": "sconosciuto",
    "absent": "assente",
}

# Vista da cui è stato visto un servizio (models.VIEW_*).
VIEW_LABELS = {
    "internal": "interna",
    "external": "esterna (floating IP)",
}


def severity_label(value):
    """Gravità in italiano; se sconosciuta, il valore grezzo."""
    return SEVERITY_LABELS.get(value, value)


def severity_css(value):
    """Classe colore del badge per la gravità; se sconosciuta, "default"."""
    return SEVERITY_CSS.get(value, "default")


def finding_label(value):
    """Tipo di segnalazione in italiano; se sconosciuto, il valore grezzo."""
    return FINDING_LABELS.get(value, value)


def classification_label(value):
    """Classificazione dell'host in italiano; se sconosciuta, il valore grezzo."""
    return CLASSIFICATION_LABELS.get(value, value)


def view_label(value):
    """Vista del servizio in italiano; se sconosciuta, il valore grezzo."""
    return VIEW_LABELS.get(value, value)


def status_label(value):
    """Stato scansione in italiano; se sconosciuto, il valore grezzo."""
    return STATUS_LABELS.get(value, value)


def trigger_label(value):
    """Origine scansione in italiano; se sconosciuta, il valore grezzo."""
    return TRIGGER_LABELS.get(value, value)


def phase_label(value):
    """Fase in italiano; se sconosciuta, il valore grezzo."""
    return PHASE_LABELS.get(value, value)


def phase_text(value):
    """Fase con la posizione: "Scoperta host e servizi (3 di 6)".

    "" se la fase è None o sconosciuta, per non scrivere "(None di 6)".
    """
    if value not in vocab.SCAN_PHASES:
        return ""
    posizione = vocab.SCAN_PHASES.index(value) + 1
    return "%s (%d di %d)" % (phase_label(value), posizione,
                             len(vocab.SCAN_PHASES))


def short_uuid(value):
    """UUID ai primi 8 caratteri + "…" (il pieno va nel tooltip del template).

    None/"" -> "—"; una stringa già corta resta com'è.
    """
    if not value:
        return "—"
    text = str(value)
    if len(text) <= 8:
        return text
    return text[:8] + "…"


def human_datetime(value):
    """Data ISO della API in "AAAA-MM-GG HH:MM" (toglie "T" e secondi).

    None/"" -> "—"; un valore senza "T" (non ISO) resta com'è.
    """
    if not value:
        return "—"
    text = str(value)
    if "T" in text:
        return text.replace("T", " ")[:16]
    return text


def enrich_scan(scan):
    """Copia della scansione con i campi già tradotti/leggibili per il template
    (etichette italiane, UUID accorciati, date brevi), per non mostrare valori grezzi.

    I template Django non chiamano le funzioni di questo modulo: i campi si
    preparano qui. Usata dal Riepilogo e dal dettaglio scansione."""
    scan = dict(scan)
    scan["status_it"] = status_label(scan.get("status"))
    scan["trigger_it"] = trigger_label(scan.get("trigger"))
    scan["id_short"] = short_uuid(scan.get("id"))
    scan["project_short"] = short_uuid(scan.get("project_id"))
    scan["created_h"] = human_datetime(scan.get("created_at"))
    scan["started_h"] = human_datetime(scan.get("started_at"))
    scan["finished_h"] = human_datetime(scan.get("finished_at"))
    return scan


def enrich_finding(finding):
    """Copia della segnalazione con gravità, colore e tipo già tradotti per il
    template. Usata dal Riepilogo, dal dettaglio scansione e dal report."""
    finding = dict(finding)
    finding["severity_it"] = severity_label(finding.get("severity"))
    finding["severity_css"] = severity_css(finding.get("severity"))
    finding["type_it"] = finding_label(finding.get("type"))
    return finding
