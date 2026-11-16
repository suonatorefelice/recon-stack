# Avanzamento scansione (fase per fase) — Piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mostrare l'avanzamento di una scansione (fase corrente, "N di 6") e aggiornare da sola la dashboard finché non è completata.

**Architecture:** Lo scanner registra la fase corrente in una nuova colonna `scans.phase`; l'API la espone; la dashboard la mostra in italiano e si auto-aggiorna mentre lo stato è transitorio (dettaglio: ricarica JS; elenco: auto-refresh di riga di Horizon). Logica testabile (fasi, etichette) in costanti/funzioni pure provate sul Mac.

**Tech Stack:** Python, SQLAlchemy + Alembic, Flask (API), Horizon/Django (dashboard), osc-lib (CLI), pytest.

**Spec:** `docs/superpowers/specs/2026-11-16-avanzamento-scansione-design.md`

**Base branch:** `dashboard-chiara` (si continua sul ramo già verificato su VM).

## Global Constraints

- Migrazione Alembic **additiva**, prossima `0006`, colonna **nullable**, solo `upgrade` (come 0001–0005: nessun `downgrade`).
- Nessuna modifica ai contenuti delle scansioni / motore esposizione / report.
- Moduli dashboard importabili sul Mac (import Horizon/Django pigri o assenti); logica testabile in funzioni pure / costanti.
- Il fixture di test `database` applica le migrazioni vere (`migration.upgrade()`): ogni test che usa `database` esercita la 0006.
- Fasi grezze (ordine = avanzamento): `perimeter, inventory, discovery, saving, external, exposure` (len 6).
- Auto-refresh SOLO mentre lo stato è transitorio (PENDING/RUNNING); si ferma a DONE/FAILED/REJECTED.
- Commit piccoli in italiano, prefisso feat/fix, con `(#1)`; nessuna attribuzione all'AI.

## Review Focus

- **Scansione vecchia (phase NULL):** dettaglio ed elenco non devono rompersi né mostrare "(None di 6)" → `phase_text(None)` restituisce "" (test Task 4); le scansioni DONE prima della 0006 restano valide (colonna nullable, Task 1).
- **Scansione fallita:** la fase resta all'ultimo passo (non azzerata), il "Motivo" è mostrato → run_scan non passa `phase=None` nel ramo FAILED (test Task 2 verifica che a DONE sia None; FAILED conserva la fase).
- **Fase sconosciuta/fuori ordine:** `phase_text` di una chiave non in `SCAN_PHASES` non deve inventare la posizione → ritorna la sola etichetta o "" (test Task 4).
- **Auto-refresh che non si ferma:** a stato finale il dettaglio non deve più ricaricare → il blocco di reload è emesso solo se `in_corso` (verifica VM Task 5; il flag `in_corso` è calcolato nella vista).
- **Migrazione applicata due volte / schema disallineato:** la colonna del modello e quella della migrazione devono combaciare → l'intera suite gira sul fixture che migra (Task 1).

---

### Task 1: Colonna `phase`, costanti e migrazione 0006

**Files:**
- Modify: `recon_stack/db/models.py` (campo `phase` su `Scan`; costanti `PHASE_*`, `SCAN_PHASES`)
- Create: `recon_stack/db/migrations/versions/0006_scan_phase.py`
- Test: `recon_stack/tests/unit/test_db.py` (nuovi test)

**Interfaces:**
- Produces: `models.PHASE_PERIMETER/INVENTORY/DISCOVERY/SAVING/EXTERNAL/EXPOSURE`; `models.SCAN_PHASES` (tuple ordinata, len 6); colonna `Scan.phase` (str|None).

- [ ] **Step 1: Scrivere i test che falliscono** in `test_db.py`:

```python
def test_scan_phases_costanti_ordinate():
    from recon_stack.db import models
    assert models.SCAN_PHASES == (
        models.PHASE_PERIMETER, models.PHASE_INVENTORY, models.PHASE_DISCOVERY,
        models.PHASE_SAVING, models.PHASE_EXTERNAL, models.PHASE_EXPOSURE)
    assert len(models.SCAN_PHASES) == 6

def test_scan_salva_e_rilegge_la_fase(database):
    from recon_stack.db import api as db, models
    scan = db.create_scan("p-1", models.TRIGGER_MANUAL)
    db.update_scan(scan.id, phase=models.PHASE_DISCOVERY)
    assert db.get_scan(scan.id).phase == models.PHASE_DISCOVERY
```

- [ ] **Step 2: Lanciare e verificare il fallimento**
Run: `.venv/bin/pytest recon_stack/tests/unit/test_db.py -k "phase" -v`
Expected: FAIL (SCAN_PHASES assente; colonna `phase` inesistente).

- [ ] **Step 3: Implementare** — in `models.py`: le 6 costanti `PHASE_*`, `SCAN_PHASES`, e `phase: Mapped[str | None] = mapped_column(String(32))` su `Scan` (commento: fase corrente, solo per mostrare l'avanzamento). In `0006_scan_phase.py`: `revision="0006"`, `down_revision="0005"`, `upgrade()` con `op.add_column("scans", sa.Column("phase", sa.String(32), nullable=True))` (nessun downgrade, come le precedenti); docstring che spiega cosa e perché.

- [ ] **Step 4: Lanciare e verificare il successo**
Run: `.venv/bin/pytest recon_stack/tests/unit/test_db.py -k "phase" -v`
Expected: PASS.

- [ ] **Step 5: Commit**
`git add recon_stack/db/models.py recon_stack/db/migrations/versions/0006_scan_phase.py recon_stack/tests/unit/test_db.py && git commit -m "feat: colonna phase e migrazione 0006 per l'avanzamento scansione (#1)"`

---

### Task 2: Lo scanner registra la fase

**Files:**
- Modify: `recon_stack/scanner/scan.py` (`run_scan`)
- Test: `recon_stack/tests/unit/test_scan.py`

**Interfaces:**
- Consumes: `models.PHASE_*` (Task 1).

- [ ] **Step 1: Scrivere il test che fallisce** in `test_scan.py` (spia su `update_scan` che registra le fasi e delega all'originale):

```python
def test_run_scan_registra_le_fasi_in_ordine(database, no_privsep, monkeypatch):
    fasi = []
    import recon_stack.scanner.scan as scan_mod
    originale = db.update_scan
    def spia(scan_id, **f):
        if "phase" in f:
            fasi.append(f["phase"])
        return originale(scan_id, **f)
    monkeypatch.setattr(scan_mod.db, "update_scan", spia)
    scan = db.create_scan("progetto-1", models.TRIGGER_MANUAL)
    scan_mod.run_scan(FakeConnection(), scan.id)
    assert fasi == [
        models.PHASE_PERIMETER, models.PHASE_INVENTORY, models.PHASE_DISCOVERY,
        models.PHASE_SAVING, models.PHASE_EXTERNAL, models.PHASE_EXPOSURE]
    # A scansione completata la fase è azzerata: si vede solo "Completata".
    assert db.get_scan(scan.id).phase is None
```

- [ ] **Step 2: Lanciare e verificare il fallimento**
Run: `.venv/bin/pytest recon_stack/tests/unit/test_scan.py -k "fasi" -v`
Expected: FAIL (`fasi` vuoto: run_scan non scrive ancora `phase`).

- [ ] **Step 3: Implementare** — in `run_scan`, una riga `db.update_scan(scan_id, phase=models.PHASE_X)` prima di: perimetro (`perimeter`), inventario (`inventory`), ciclo di scoperta (`discovery`), `save_hosts` (`saving`), `_discover_external` (`external`), `compute_and_save` (`exposure`). Nel ramo DONE aggiungere `phase=None` alla `update_scan(status=SCAN_DONE, ...)`. Il ramo FAILED resta invariato (la fase conserva dove si è fermata).

- [ ] **Step 4: Lanciare e verificare il successo**
Run: `.venv/bin/pytest recon_stack/tests/unit/test_scan.py -v`
Expected: PASS (nuovo test + quelli esistenti di run_scan).

- [ ] **Step 5: Commit**
`git add recon_stack/scanner/scan.py recon_stack/tests/unit/test_scan.py && git commit -m "feat: lo scanner registra la fase corrente della scansione (#1)"`

---

### Task 3: L'API espone la fase

**Files:**
- Modify: `recon_stack/api/v1.py` (`_scan_dict`)
- Test: `recon_stack/tests/unit/test_v1.py`

**Interfaces:**
- Produces: campo `"phase"` nei dizionari scansione di `/v1/scans` e `/v1/scans/<id>`.

- [ ] **Step 1: Scrivere il test che fallisce** in `test_v1.py`: creata una scansione con `phase` impostata, `GET /v1/scans/<id>` la restituisce nel JSON (`data["phase"] == models.PHASE_DISCOVERY`). Seguire lo stile dei test esistenti del modulo (client Flask di test + fixture `database`).

- [ ] **Step 2: Lanciare e verificare il fallimento**
Run: `.venv/bin/pytest recon_stack/tests/unit/test_v1.py -k "phase" -v`
Expected: FAIL (chiave `phase` assente).

- [ ] **Step 3: Implementare** — in `_scan_dict` aggiungere `"phase": scan.phase`.

- [ ] **Step 4: Lanciare e verificare il successo**
Run: `.venv/bin/pytest recon_stack/tests/unit/test_v1.py -k "phase" -v`
Expected: PASS.

- [ ] **Step 5: Commit**
`git add recon_stack/api/v1.py recon_stack/tests/unit/test_v1.py && git commit -m "feat: l'API include la fase nella rappresentazione della scansione (#1)"`

---

### Task 4: Etichette delle fasi (dashboard)

**Files:**
- Modify: `recon_stack/dashboard/recon/labels.py`
- Test: `recon_stack/tests/unit/test_dashboard_labels.py`

**Interfaces:**
- Consumes: `models.SCAN_PHASES` (Task 1).
- Produces: `PHASE_LABELS` (dict); `phase_label(key) -> str` (fallback al grezzo); `phase_text(key) -> str` ("Scoperta host e servizi (3 di 6)"; "" se `key` è None/sconosciuta/fuori da SCAN_PHASES).

- [ ] **Step 1: Scrivere i test che falliscono** in `test_dashboard_labels.py`:

```python
def test_phase_label_e_testo_con_posizione():
    assert labels.phase_label("discovery") == "Scoperta host e servizi"
    assert labels.phase_text("discovery") == "Scoperta host e servizi (3 di 6)"
    assert labels.phase_text("perimeter").endswith("(1 di 6)")
    assert labels.phase_text("exposure").endswith("(6 di 6)")

def test_phase_text_robusto():
    assert labels.phase_text(None) == ""
    assert labels.phase_text("boh") == ""          # non in SCAN_PHASES: niente posizione
    assert labels.phase_label("boh") == "boh"      # fallback al grezzo
```

- [ ] **Step 2: Lanciare e verificare il fallimento**
Run: `.venv/bin/pytest recon_stack/tests/unit/test_dashboard_labels.py -k "phase" -v`
Expected: FAIL (funzioni assenti).

- [ ] **Step 3: Implementare** — `PHASE_LABELS` (perimeter→"Perimetro", inventory→"Inventario", discovery→"Scoperta host e servizi", saving→"Salvataggio", external→"Vista esterna", exposure→"Esposizione"); `phase_label` con `.get(k, k)`; `phase_text` che, se `k in models.SCAN_PHASES`, ritorna `"<label> (<indice+1> di <len>)"`, altrimenti `""`. Import di `models` (puro, già usato altrove).

- [ ] **Step 4: Lanciare e verificare il successo**
Run: `.venv/bin/pytest recon_stack/tests/unit/test_dashboard_labels.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**
`git add recon_stack/dashboard/recon/labels.py recon_stack/tests/unit/test_dashboard_labels.py && git commit -m "feat: etichette e posizione delle fasi per la dashboard (#1)"`

---

### Task 5: Dashboard — dettaglio scansione con fase e auto-ricarica

**Files:**
- Modify: `recon_stack/dashboard/recon/scans/views.py` (DetailView), `scans/templates/scans/detail.html`

**Interfaces:**
- Consumes: `labels.phase_text` (Task 4); campo `phase` dalla API (Task 3).

- [ ] **Step 1: Vista** — in `DetailView.get_context_data`, arricchire lo scan con `phase_text = labels.phase_text(scan.get("phase"))` e `in_corso = scan.get("status") in (models.SCAN_PENDING, models.SCAN_RUNNING)`.

- [ ] **Step 2: Template** — in `detail.html`: se `scan.in_corso`, accanto allo stato una rotella + `{{ scan.phase_text }}` ("⟳ In corso — Scoperta host e servizi (3 di 6)"); in fondo, SOLO se `scan.in_corso`, `<script>setTimeout(function(){location.reload();}, 4000);</script>`.

- [ ] **Step 3: Test strutturali** (il rendering si prova sulla VM; qui niente regressioni):
Run: `.venv/bin/pytest recon_stack/tests/unit -k dashboard -v`
Expected: PASS.

- [ ] **Step 4: Commit**
`git add recon_stack/dashboard/recon/scans/views.py recon_stack/dashboard/recon/scans/templates/scans/detail.html && git commit -m "feat: il dettaglio scansione mostra la fase e si ricarica fino a fine (#1)"`

---

### Task 6: Dashboard — elenco con auto-refresh di riga

**Files:**
- Modify: `recon_stack/dashboard/recon/scans/tables.py`

**Interfaces:**
- Consumes: `labels.*` (Task 4); `ReconClient.get_scan` (per la riga singola).

- [ ] **Step 1: Implementare** — `class UpdateRow(tables.Row): ajax = True` con `get_data(self, request, scan_id)` che rilegge la scansione dalla API (`api.reconclient(request).get_scan(scan_id)`, poi `api.wrap`); in `ScansTable.Meta` aggiungere `row_class = UpdateRow` e `status_columns = ["status"]`; rendere la colonna `status` con `status=True` e `status_choices` che segnano finali `DONE/FAILED/REJECTED` (PENDING/RUNNING restano transitori → Horizon ri-sonda la riga). La cella stato, se in corso, mostra "In corso — <fase>" (via `labels.phase_text`), altrimenti `labels.status_label`.

- [ ] **Step 2: Test strutturali** (l'auto-refresh si prova sulla VM):
Run: `.venv/bin/pytest recon_stack/tests/unit -k dashboard -v`
Expected: PASS.

- [ ] **Step 3: Commit**
`git add recon_stack/dashboard/recon/scans/tables.py && git commit -m "feat: l'elenco scansioni aggiorna da solo la riga in corso con la fase (#1)"`

---

### Task 7: CLI `recon scan show` mostra la fase

**Files:**
- Modify: `recon_stack/osc/commands.py`
- Test: `recon_stack/tests/unit/test_osc_commands.py`

**Interfaces:**
- Consumes: campo `phase` dalla API (Task 3).

- [ ] **Step 1: Scrivere il test che fallisce** in `test_osc_commands.py`: `recon scan show` di una scansione con `phase` impostata include "Fase" e l'etichetta/valore nell'output (seguire lo stile dei test osc esistenti, con client finto).

- [ ] **Step 2: Lanciare e verificare il fallimento**
Run: `.venv/bin/pytest recon_stack/tests/unit/test_osc_commands.py -k "fase or phase" -v`
Expected: FAIL.

- [ ] **Step 3: Implementare** — nel comando ShowOne della scansione, aggiungere la colonna "Fase" col valore `phase` (grezzo o tramite una piccola mappa locale; il CLI non importa `labels` della dashboard).

- [ ] **Step 4: Lanciare e verificare il successo**
Run: `.venv/bin/pytest recon_stack/tests/unit/test_osc_commands.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**
`git add recon_stack/osc/commands.py recon_stack/tests/unit/test_osc_commands.py && git commit -m "feat: recon scan show mostra la fase della scansione (#1)"`

---

## Verifica finale (VM DevStack)

Deploy del ramo sulla VM (push + fetch + restart recon-api/recon-scanner/apache2). Avvia una scansione di `recon-demo`: il dettaglio mostra "In corso — <fase> (N di 6)" che avanza e si ferma su "Completata" senza ricaricare a mano; l'elenco aggiorna da solo la riga in corso; `recon scan show` stampa la fase; le 7 segnalazioni restano quelle; nessuna regressione sulle scansioni vecchie (phase NULL).
