# Etichette italiane e colori per la dashboard.
#
# I dati arrivano dalla API con i valori "grezzi" salvati nel database (in
# inglese: high/medium/low, DONE/RUNNING, overexposed, ...). Qui, in un posto
# solo, li traduciamo in italiano e associamo a ognuno il colore del badge, così
# tabelle, template e pannello Riepilogo leggono da qui e non ripetono le stesse
# mappe. Sono funzioni pure, senza import di Horizon/Django: si provano sul Mac.
#
# Ogni funzione ripiega sul valore grezzo se non lo conosce (.get(v, v)): se
# domani la API aggiunge un tipo nuovo, la pagina mostra il nome tecnico invece
# di rompersi.


from recon_stack.db import models


# Gravità (models.SEVERITY_*): etichetta leggibile e classe colore del badge.
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

# Tipi di segnalazione (models.FINDING_*): nome tecnico -> frase breve italiana.
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

# Stato della scansione (models.SCAN_*).
STATUS_LABELS = {
    "PENDING": "In attesa",
    "RUNNING": "In corso",
    "DONE": "Completata",
    "FAILED": "Fallita",
    "REJECTED": "Rifiutata",
}

# Origine della scansione (models.TRIGGER_*).
TRIGGER_LABELS = {
    "manual": "Manuale",
    "periodic": "Periodica",
}

# Fasi di una scansione in corso (models.PHASE_*): nome tecnico -> etichetta.
PHASE_LABELS = {
    "perimeter": "Perimetro",
    "inventory": "Inventario",
    "discovery": "Scoperta host e servizi",
    "saving": "Salvataggio",
    "external": "Vista esterna",
    "exposure": "Esposizione",
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

    Restituisce "" se la fase è None o non è una fase nota (models.SCAN_PHASES):
    così non mostriamo una posizione inventata e il dettaglio di una scansione
    senza fase (vecchia o non in corso) non scrive "(None di 6)".
    """
    if value not in models.SCAN_PHASES:
        return ""
    posizione = models.SCAN_PHASES.index(value) + 1
    return "%s (%d di %d)" % (phase_label(value), posizione,
                             len(models.SCAN_PHASES))


def short_uuid(value):
    """UUID accorciato ai primi 8 caratteri + "…", per non riempire la tabella.

    Il valore pieno resta disponibile (lo mettiamo nel tooltip del template).
    `None` o stringa vuota -> "—"; una stringa già corta resta com'è.
    """
    if not value:
        return "—"
    text = str(value)
    if len(text) <= 8:
        return text
    return text[:8] + "…"


def human_datetime(value):
    """Data ISO della API in forma leggibile "AAAA-MM-GG HH:MM".

    La API manda date in formato ISO ("2026-11-16T14:32:00.123456"); qui
    togliamo la "T" e i secondi/microsecondi. `None` o "" -> "—"; un valore che
    non è una data ISO (niente "T") resta com'è, senza errori.
    """
    if not value:
        return "—"
    text = str(value)
    if "T" in text:
        return text.replace("T", " ")[:16]
    return text
