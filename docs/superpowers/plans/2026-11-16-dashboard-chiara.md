# Dashboard più chiara — Piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendere la dashboard Horizon di Recon-Stack chiara per non esperti: etichette italiane, badge gravità colorati, date leggibili, UUID accorciati, un pannello "Riepilogo" d'atterraggio e un elenco progetti nel form di avvio.

**Architecture:** Tutto lato presentazione (ADR 0010, 0002): nessuna modifica ad API/DB/CLI/scanner. Un modulo `labels.py` di funzioni pure (mappe italiano + colori + UUID accorciato) raccoglie la logica testabile sul Mac; tabelle, template e il nuovo pannello la consumano. Il Riepilogo aggrega chiamando la API esistente; l'aggregazione vive in una funzione pura `build_summary(client)` così è testabile senza Horizon, mentre la vista Django la usa soltanto.

**Tech Stack:** Python, Horizon/Django (plugin dashboard), Bootstrap (classi già incluse in Horizon), pytest.

**Spec:** `docs/superpowers/specs/2026-11-16-dashboard-chiara-design.md`

## Global Constraints

- Nessuna modifica ad API `/v1`, DB, migrazioni, CLI/osc, scanner, exposure, report.
- Ogni modulo nuovo deve restare importabile sul Mac: import di Horizon/Django **pigri** (dentro le funzioni) o assenti. La logica testabile sta in funzioni pure senza import Horizon/Django.
- Valori grezzi esatti (da `db/models.py`): stato ∈ {PENDING, RUNNING, DONE, FAILED, REJECTED}; origine ∈ {manual, periodic}; gravità ∈ {high, medium, low, info}; 8 tipi finding (useless_rule, latent_service, overexposed, externally_reachable, unknown_exposed, wasted_floating_ip, external_only, no_port_security).
- Commit piccoli in italiano, prefisso feat/fix/docs, con `(#1)`; nessuna attribuzione all'AI.
- Test unitari sul Mac (`tox`/pytest); il codice `recon/**` che dipende da Horizon si verifica sulla VM in coda.

## Review Focus

- **API non raggiungibile / nessuna scansione ancora:** il Riepilogo deve mostrare uno stato vuoto ("nessuna scansione"), non un errore 500 → test in Task 2 (client che solleva, e `list_scans` vuoto).
- **Valore grezzo fuori mappa** (gravità/stato/tipo/origine sconosciuti): le funzioni label devono ripiegare sul valore grezzo, mai sollevare → test in Task 1.
- **UUID assente o corto** (`None`, stringa < 8 char): `short_uuid` non deve rompersi → test in Task 1.
- **Keystone non disponibile nel form Avvia scansione:** deve ripiegare sul campo libero (incolla UUID), non impedire di avviare scansioni → verifica VM (Task 5), codice difensivo.
- **Gravità senza colore noto:** `severity_css` ripiega su "default" (badge grigio), nessuna classe CSS inventata → test in Task 1.

---

### Task 1: Modulo etichette `labels.py` (funzioni pure)

**Files:**
- Create: `recon_stack/dashboard/recon/labels.py`
- Test: `recon_stack/tests/unit/test_dashboard_labels.py`

**Interfaces:**
- Produces:
  - `SEVERITY_LABELS, SEVERITY_CSS, FINDING_LABELS, STATUS_LABELS, TRIGGER_LABELS` (dict)
  - `severity_label(v) -> str`, `severity_css(v) -> str`, `finding_label(v) -> str`, `status_label(v) -> str`, `trigger_label(v) -> str` (fallback al valore grezzo, o "default" per css ignoto)
  - `short_uuid(v) -> str` (primi 8 char + "…"; `None`/"" → "—"; stringa ≤ 8 → invariata)

- [ ] **Step 1: Scrivere il test che fallisce** in `test_dashboard_labels.py`:

```python
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
```

- [ ] **Step 2: Lanciare il test e verificare che fallisca**
Run: `python -m pytest recon_stack/tests/unit/test_dashboard_labels.py -v`
Expected: FAIL (ModuleNotFoundError: labels).

- [ ] **Step 3: Scrivere `labels.py`** — le cinque mappe coi valori italiani (gravità: Grave/Media/Bassa/Informativa; css: danger/warning/info/default; stato: In attesa/In corso/Completata/Fallita/Rifiutata; origine: Manuale/Periodica; 8 finding con testi coerenti col GLOSSARY) e le funzioni helper con `.get(v, v)` (css ignoto → "default"). Commento d'apertura: cosa fa e perché (unico posto per traduzioni/colori, funzioni pure testabili sul Mac). Nessun import Horizon/Django.

- [ ] **Step 4: Lanciare il test e verificare che passi**
Run: `python -m pytest recon_stack/tests/unit/test_dashboard_labels.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**
`git add recon_stack/dashboard/recon/labels.py recon_stack/tests/unit/test_dashboard_labels.py && git commit -m "feat: etichette italiane e colori per la dashboard (#1)"`

---

### Task 2: Pannello Riepilogo

**Files:**
- Create: `recon_stack/dashboard/recon/overview/__init__.py`, `panel.py`, `urls.py`, `views.py`, `summary.py`, `templates/overview/index.html`
- Modify: `recon_stack/dashboard/recon/dashboard.py` (panels + default_panel)
- Test: `recon_stack/tests/unit/test_dashboard_overview.py`

**Interfaces:**
- Consumes: `labels.*` (Task 1); `ReconClient.list_scans(status=...)`, `get_scan_exposure(scan_id)` (già esistenti).
- Produces: `summary.build_summary(client, top=5) -> dict` con chiavi: `scan` (dict o None), `counts` (dict gravità→int, incluse le zero), `top_findings` (lista, già ordinata per gravità), `error` (bool). Funzione pura, nessun import Horizon/Django.

- [ ] **Step 1: Scrivere il test che fallisce** in `test_dashboard_overview.py` con un client finto:

```python
from recon_stack.dashboard.recon.overview import summary

class _Client:
    def __init__(self, scans=None, findings=None, boom=False):
        self._scans, self._findings, self._boom = scans or [], findings or [], boom
    def list_scans(self, status=None):
        if self._boom: raise RuntimeError("api giù")
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
```

- [ ] **Step 2: Lanciare il test e verificare che fallisca**
Run: `python -m pytest recon_stack/tests/unit/test_dashboard_overview.py -v`
Expected: FAIL (modulo summary assente).

- [ ] **Step 3: Scrivere `summary.build_summary`** in `overview/summary.py`: prende l'ultima scansione DONE (`client.list_scans(status="DONE")`, prima della lista; se vuota → `scan=None`); se presente, legge le segnalazioni, conta per gravità (dizionario inizializzato a 0 per tutte e quattro) e taglia le prime `top`. Tutto dentro `try/except` → su eccezione ritorna `{"scan": None, "counts": {...0}, "top_findings": [], "error": True}`. Nessun import Horizon/Django.

- [ ] **Step 4: Scrivere i file del pannello** (verificati sulla VM, qui devono solo soddisfare i test strutturali esistenti):
  - `panel.py`: classe `Overview(horizon.Panel)`, `name = _("Riepilogo")`, `slug = "overview"`.
  - `views.py`: `IndexView(generic.TemplateView)`, `template_name = "recon/overview/index.html"`; `get_context_data` costruisce `api.reconclient(request)`, chiama `summary.build_summary(client)` e passa il dict al contesto, applicando le etichette/colori di `labels` nel template.
  - `urls.py`: rotta vuota → `IndexView`.
  - `templates/overview/index.html`: schede Bootstrap (ultima scansione con stato+data leggibili via `labels`/filtro `date`), riga di conteggi per gravità coi badge colorati (`label label-<css>`), tabellina "Da guardare subito" (tipo+gravità tradotti, IP, porta, link al dettaglio scansione). Stato vuoto se `scan is None` o `error`.
  - `__init__.py`: vuoto.
  - `dashboard.py`: `panels = ("overview", "hosts", "services", "scans")`, `default_panel = "overview"`.

- [ ] **Step 5: Lanciare i test e verificare che passino** (logica + struttura template/url già coperte dai test esistenti):
Run: `python -m pytest recon_stack/tests/unit/test_dashboard_overview.py recon_stack/tests/unit/test_dashboard_templates.py recon_stack/tests/unit/test_dashboard_urls.py -v`
Expected: PASS (il nuovo template è nel posto giusto, la rotta è coerente).

- [ ] **Step 6: Commit**
`git add recon_stack/dashboard/recon/overview recon_stack/dashboard/recon/dashboard.py recon_stack/tests/unit/test_dashboard_overview.py && git commit -m "feat: pannello Riepilogo come pagina d'atterraggio della dashboard (#1)"`

---

### Task 3: Pulizia delle tabelle (host, servizi, scansioni)

**Files:**
- Modify: `recon_stack/dashboard/recon/hosts/tables.py`, `services/tables.py`, `scans/tables.py`

**Interfaces:**
- Consumes: `labels.*` (Task 1). Nessun nuovo output.

- [ ] **Step 1: Applicare le etichette** usando `labels` come funzioni di cella (`tables.Column(funzione, ...)`):
  - `scans/tables.py`: `status`→`labels.status_label` (badge via `status` con `classes`/template di cella se serve il colore), `trigger`→`labels.trigger_label`, `created_at`→data leggibile, `id`/`project_id`→`labels.short_uuid`.
  - `hosts/tables.py`: `network_id`→`labels.short_uuid`; la classificazione resta tradotta com'è.
  - `services/tables.py`: nessun UUID in vista; lasciare invariata salvo rifiniture di coerenza.

- [ ] **Step 2: Lanciare i test strutturali** (le tabelle si verificano sulla VM; qui niente regressioni):
Run: `python -m pytest recon_stack/tests/unit -k dashboard -v`
Expected: PASS.

- [ ] **Step 3: Commit**
`git add recon_stack/dashboard/recon/*/tables.py && git commit -m "feat: tabelle dashboard con etichette, date leggibili e UUID accorciati (#1)"`

---

### Task 4: Pulizia dei dettagli (scansione e host)

**Files:**
- Modify: `recon_stack/dashboard/recon/scans/templates/scans/detail.html`, `hosts/templates/hosts/detail.html`
- Modify: `recon_stack/dashboard/recon/scans/views.py` (passare etichette/colori al contesto se il template non può chiamarle da solo)

**Interfaces:**
- Consumes: `labels.*` (Task 1).

- [ ] **Step 1: Aggiornare `scans/detail.html`**: gravità come badge colorato (`labels.severity_label` + `labels.severity_css`), tipo come `labels.finding_label`, stato/origine tradotti, date leggibili (filtro `date`), UUID accorciati con l'originale nel `title` (tooltip). Dato che i template Django non importano Python a piacere, pre-tradurre nel `views.py` (arricchire ogni finding con `severity_it`, `severity_css`, `type_it`) e nel template usare quei campi.

- [ ] **Step 2: Aggiornare `hosts/detail.html`**: classificazione tradotta (riuso della mappa già esistente nella tabella), UUID (rete, porta Neutron) accorciati con tooltip.

- [ ] **Step 3: Lanciare i test strutturali**:
Run: `python -m pytest recon_stack/tests/unit -k dashboard -v`
Expected: PASS.

- [ ] **Step 4: Commit**
`git add recon_stack/dashboard/recon/scans/templates/scans/detail.html recon_stack/dashboard/recon/hosts/templates/hosts/detail.html recon_stack/dashboard/recon/scans/views.py && git commit -m "feat: dettagli scansione e host con gravità colorata ed etichette chiare (#1)"`

---

### Task 5: Avvia scansione con elenco progetti

**Files:**
- Modify: `recon_stack/dashboard/recon/scans/forms.py`

**Interfaces:**
- Consumes: Keystone via `openstack_dashboard.api.keystone.tenant_list` (import pigro).

- [ ] **Step 1: In `StartScanForm.__init__`** provare a costruire un `ChoiceField` con i progetti (etichetta = nome, valore = id) leggendoli da Keystone con import pigro dentro `try/except`; su errore o elenco vuoto, mantenere il `CharField` attuale (incolla UUID). `handle()` invariato. Codice difensivo: un fallimento di Keystone non deve impedire di avviare una scansione.

- [ ] **Step 2: Lanciare i test strutturali** (la logica Keystone si prova sulla VM):
Run: `python -m pytest recon_stack/tests/unit -k dashboard -v`
Expected: PASS.

- [ ] **Step 3: Commit**
`git add recon_stack/dashboard/recon/scans/forms.py && git commit -m "feat: Avvia scansione sceglie il progetto da un elenco invece dell'UUID (#1)"`

---

### Task 6: Documentazione

**Files:**
- Modify: `docs/architettura*` (sezione dashboard), `README.md`, `CLAUDE.md` se opportuno

- [ ] **Step 1: Annotare** nelle note dashboard: nuovo pannello Riepilogo, etichette/colori, UUID accorciati, elenco progetti nel form; ricordare che `recon/**` si verifica sulla VM e aggiungere alla checklist della prossima demo i controlli di questo piano (Riepilogo coi conteggi giusti, badge colorati, date leggibili, dropdown progetti con ripiego).

- [ ] **Step 2: Commit**
`git add -A docs README.md CLAUDE.md && git commit -m "docs: nota dashboard più chiara e verifiche VM (#1)"`

---

## Verifica finale (VM DevStack)

In coda, nella prossima demo (vedi appunti): Riepilogo mostra l'ultima scansione e i conteggi corretti; badge gravità colorati; date leggibili; dropdown progetti funziona e ripiega se Keystone non risponde; nessuna regressione sui pannelli esistenti. Restano le 7 segnalazioni attese.
