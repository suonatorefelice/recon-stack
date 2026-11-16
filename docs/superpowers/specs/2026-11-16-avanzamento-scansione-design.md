# Design — Avanzamento della scansione (fase per fase)

Data: 2026-11-16 · Issue #1 · Autore: Pasquale (rivisto con Claude)

## Intento e perché

Oggi, avviata una scansione, lo stato resta "In corso" fino alla fine e non si
aggiorna da solo: l'utente deve ricaricare a mano per sapere se è finita, senza
alcun senso di avanzamento. Vogliamo che la dashboard **mostri a che punto è**
la scansione (la fase corrente, es. "Scoperta servizi (3 di 6)") e che la
pagina **si aggiorni da sola** finché la scansione non è completata, atterrando
sui risultati senza ricaricare a mano.

Scelta fatta in brainstorming: **Strada B** (fase corrente, non solo una rotella
generica), mostrata sul **dettaglio scansione** e nella **colonna Stato
dell'elenco**.

## Obiettivi

- Lo scanner registra la **fase corrente** della scansione mentre procede
  (perimetro → inventario → scoperta → salvataggio → vista esterna →
  esposizione).
- L'API espone la fase; la dashboard la mostra in italiano con la posizione
  ("3 di 6").
- La **pagina di dettaglio** di una scansione in corso si **auto-aggiorna**
  (ricarica ogni pochi secondi) finché lo stato non è finale, poi mostra i
  risultati.
- L'**elenco scansioni** aggiorna da solo la riga di una scansione in corso
  (meccanismo di auto-refresh di riga di Horizon), mostrando stato + fase.
- A scansione **completata** la fase sparisce (si vede solo "Completata"); se
  **fallita**, la fase resta a indicare dove si è fermata (oltre al "Motivo").

## Non-obiettivi

- Niente percentuale numerica (Strada C scartata: prima della scoperta non si
  conosce il totale, sarebbe un numero finto).
- Niente WebSocket/push: l'aggiornamento è a *polling* (ricarica periodica),
  coerente con Horizon e semplice da difendere.
- Nessuna modifica ai contenuti delle scansioni, al motore di esposizione, al
  report.

## Anti-obiettivi

- Rompere scansioni esistenti o il flusso attuale: la colonna nuova è
  **nullable**, le scansioni vecchie (phase NULL) restano valide.
- Un auto-refresh che non si ferma mai: deve ricaricare **solo** mentre lo stato
  è transitorio (PENDING/RUNNING) e smettere a DONE/FAILED/REJECTED.
- Introdurre un errore visibile solo sulla VM: la logica testabile (fasi,
  etichette) sta in funzioni/costanti provate sul Mac; auto-refresh e tabella si
  verificano sulla VM.

## Vincoli

- Migrazione Alembic additiva (prossima: **0006**), colonna nullable.
- Moduli dashboard importabili sul Mac (import Horizon/Django pigri o assenti);
  la logica testabile in funzioni pure / costanti.
- Commit piccoli in italiano con `(#1)`; test unitari sul Mac; verifica VM in
  coda.

## Approcci considerati

Il tipo di avanzamento è stato deciso in brainstorming (A rotella / B fase / C
percentuale → **B**). Restano scelte realizzative, prese qui come mie calls:

- **Dove salvare la fase.** Nuova colonna `scans.phase` (scelta) vs riuso di un
  campo esistente (scartato: `fault`/`perimeter` hanno altro significato, sarebbe
  confuso).
- **Come auto-aggiornare il dettaglio.** Un piccolo `setTimeout(reload)` iniettato
  nel template solo se lo stato è transitorio (scelto: zero dipendenze, si ferma
  da solo a stato finale) vs `<meta http-equiv=refresh>` (scartato: va nell'head,
  più scomodo nei template dei pannelli).
- **Come auto-aggiornare l'elenco.** Il meccanismo nativo di Horizon di
  auto-refresh di riga (`Row.ajax = True` + `get_data(request, id)` + colonna
  `status`): è lo stesso usato dalla tabella delle istanze Nova. Scelto perché
  idiomatico; da confermare sulla VM.

## Come è fatto (decisioni prese)

### 1. Database e modello

- `recon_stack/db/models.py`:
  - nuova colonna `phase: Mapped[str | None] = mapped_column(String(32))` su `Scan`.
  - costanti `PHASE_PERIMETER="perimeter"`, `PHASE_INVENTORY="inventory"`,
    `PHASE_DISCOVERY="discovery"`, `PHASE_SAVING="saving"`,
    `PHASE_EXTERNAL="external"`, `PHASE_EXPOSURE="exposure"`.
  - `SCAN_PHASES = (PHASE_PERIMETER, PHASE_INVENTORY, PHASE_DISCOVERY,
    PHASE_SAVING, PHASE_EXTERNAL, PHASE_EXPOSURE)` (ordine = avanzamento; lunghezza
    = il "di 6").
- Migrazione `recon_stack/db/migrations/versions/0006_scan_phase.py`:
  `down_revision = "0005"`; `add_column("scans", Column("phase", String(32), nullable=True))`;
  `downgrade` la rimuove.

`db.update_scan(scan_id, **fields)` è già generico: `update_scan(id, phase=...)`
funziona senza modifiche.

### 2. Scanner (`recon_stack/scanner/scan.py`)

In `run_scan`, prima di ciascuno dei passi, una riga
`db.update_scan(scan_id, phase=models.PHASE_X)`:

| Passo di run_scan | fase |
| --- | --- |
| 2. perimetro | `perimeter` |
| 3. inventario | `inventory` |
| 4. scoperta host+servizi | `discovery` |
| 5. salvataggio | `saving` |
| 6. vista esterna | `external` |
| 7. esposizione | `exposure` |

A fine corsa: nel ramo DONE `update_scan(..., status=SCAN_DONE, phase=None)`
(la fase sparisce). Nel ramo FAILED **non** si azzera la fase (resta a indicare
dove si è fermata).

### 3. API (`recon_stack/api/v1.py`)

`_scan_dict` aggiunge `"phase": scan.phase`. Nessun'altra modifica.

### 4. CLI osc (coerenza)

`recon_stack/osc/commands.py`: il comando `recon scan show` aggiunge una riga
"Fase" quando presente. (Facoltativo ma coerente; non cambia l'elenco.)

### 5. Etichette dashboard (`recon_stack/dashboard/recon/labels.py`)

- `PHASE_LABELS`: perimeter→"Perimetro", inventory→"Inventario",
  discovery→"Scoperta host e servizi", saving→"Salvataggio",
  external→"Vista esterna", exposure→"Esposizione".
- `phase_label(key) -> str` (fallback al grezzo).
- `phase_text(key) -> str` che unisce etichetta e posizione:
  "Scoperta host e servizi (3 di 6)"; `""` se `key` è None/sconosciuta
  (nessuna posizione inventata). La posizione viene da `models.SCAN_PHASES`.

### 6. Dashboard — dettaglio scansione

- `scans/views.py` (DetailView): arricchisce lo scan con
  `phase_text = labels.phase_text(scan["phase"])` e un flag
  `in_corso = status in (PENDING, RUNNING)`.
- `scans/templates/scans/detail.html`: se `in_corso`, mostra accanto allo stato
  una rotella + `phase_text` ("⟳ In corso — Scoperta host e servizi (3 di 6)"),
  e in fondo `<script>setTimeout(function(){location.reload();}, 4000)</script>`
  **solo** se `in_corso` (si ferma da solo a stato finale).

### 7. Dashboard — elenco scansioni

- `scans/tables.py`:
  - `class UpdateRow(tables.Row): ajax = True; def get_data(self, request, scan_id):`
    rilegge la scansione dalla API e la restituisce come oggetto.
  - `ScansTable.Meta`: `row_class = UpdateRow`, `status_columns = ["status"]`;
    la colonna `status` diventa `status=True` con `status_choices` che segnano
    finali DONE/FAILED/REJECTED (così PENDING/RUNNING sono transitori e Horizon
    li ri-sonda da solo).
  - La cella stato mostra, se in corso, "In corso — <fase>"; altrimenti
    l'etichetta dello stato.

## Test

- Sul Mac:
  - `labels.phase_label` / `phase_text` (pure): etichette, posizione "N di 6",
    fallback su None/sconosciuto.
  - `models.SCAN_PHASES`: lunghezza 6 e ordine.
  - `scan.run_scan` registra le fasi: spiando `db.update_scan` (monkeypatch) si
    verifica che le fasi compaiano **in ordine** durante una corsa riuscita e
    che a DONE `phase` finisca a None (rilettura dal DB).
  - `_scan_dict` include `phase` (test API esistenti o diretto).
  - la migrazione 0006 si applica (test migrazioni esistente, se presente;
    altrimenti upgrade su DB temporaneo).
- Sulla VM (in coda): avvio scansione reale, la pagina di dettaglio e l'elenco
  mostrano la fase e si aggiornano da soli fino a Completata; nessuna
  regressione sulle scansioni vecchie (phase NULL).

## Verifica finale (VM DevStack)

Avvia una scansione di `recon-demo`: il dettaglio mostra "In corso — <fase> (N
di 6)" che avanza e si ferma su "Completata" con i risultati, senza ricaricare a
mano; l'elenco aggiorna la riga da solo; le 7 segnalazioni restano quelle.

## Lasciato al costruttore

- Testi italiani definitivi delle fasi (coerenti col GLOSSARY).
- Intervallo di ricarica (proposta: 4 secondi).
- Dettaglio dell'idioma Horizon di auto-refresh di riga (status_choices,
  get_data) secondo cosa funziona sulla VM.
- Se il ramo parte da `main` o continua su `dashboard-chiara` (decisione di
  integrazione ancora aperta).
