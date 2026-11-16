# Design — Dashboard più chiara e meno tecnica

Data: 2026-11-16 · Issue #1 · Autore: Pasquale (rivisto con Claude)

## Intento e perché

La dashboard Horizon di Recon-Stack mostra tutti i dati giusti, ma "grezzi":
gravità e tipi di segnalazione in inglese e senza colore, stati e origini
scansione grezzi, UUID ovunque, e si atterra su una tabella nuda. Per chi non
è dell'infrastruttura è difficile da leggere. Vogliamo una dashboard **chiara
per non esperti**: etichette in italiano, colori a colpo d'occhio sulla
gravità, date leggibili, e una pagina di **Riepilogo** che riassuma l'ultima
scansione.

"Accessibile" qui significa *comprensibile*, non conformità a11y (contrasto,
screen reader, ARIA) — quella resta fuori scope.

## Obiettivi

- Nuovo pannello **Riepilogo**, pagina d'atterraggio della dashboard, che
  riassume l'ultima scansione completata: stato, conteggio segnalazioni per
  gravità, e le più gravi in breve.
- **Etichette italiane** per: gravità, tipo di segnalazione, stato scansione,
  origine (trigger).
- **Badge colorati** per la gravità (rosso/arancio/giallo/grigio) nelle tabelle
  e nel dettaglio.
- **Date leggibili** (es. "16 nov 2026 14:32") al posto dei timestamp grezzi.
- **UUID più gentili**: nome dove è già nei dati; altrove UUID accorciato con
  l'originale nel tooltip.
- **Avvia scansione**: elenco a tendina dei progetti (da Keystone) invece di
  incollare l'UUID a mano, con ritorno al campo libero se l'elenco non è
  disponibile.

## Non-obiettivi

- Nessuna modifica alla API `/v1`, al DB o alle migrazioni (ADR 0002 resta: la
  dashboard è solo presentazione, aggrega lato client).
- Nessuna modifica a CLI/osc, scanner, exposure engine, report.
- Nessuna conformità a11y formale.
- Nessuna risoluzione dei nomi via Keystone/Neutron nelle tabelle (scelta
  "pragmatica": solo dati già presenti + UUID accorciato). Il dropdown del form
  è l'unica eccezione che tocca Keystone, perché lì il valore vero serve.

## Anti-obiettivi (cosa sarebbe un fallimento anche se "funziona")

- Rompere qualcosa che va già e che si vede solo sulla VM (è un progetto
  d'esame già verificato): ogni aggiunta deve degradare con grazia se una
  chiamata fallisce.
- Rendere la dashboard "carina" ma meno fedele ai dati (es. nascondere l'UUID
  vero quando serve a difendere il progetto): l'originale resta sempre
  raggiungibile (tooltip).

## Vincoli

- Horizon/Django disponibili solo sulla VM: i moduli devono restare
  importabili e testabili sul Mac (import pigri come già in `dashboard/api.py`).
- Il client della dashboard (`ReconClient`) non ha "ultima scansione": il
  Riepilogo usa `list_scans(status="DONE")` e prende la prima (da verificare
  che l'ordine API sia dal più recente; in implementazione si conferma e, se
  serve, si ordina per `created_at` lato vista).
- Si continua con commit piccoli in italiano che citano (#1); test unitari sul
  Mac; verifica end-to-end sulla VM in fondo.

## Approcci considerati

- **A — Riepilogo calcolato nella dashboard (SCELTO).** La vista Horizon chiama
  la API esistente e compone le schede. Nessuna modifica API/DB, rischio basso
  sulla VM. Svantaggio: l'aggregazione vive nella presentazione, non riusabile
  da CLI.
- **B — Endpoint API `/v1/overview`.** La API aggrega, la dashboard mostra.
  Più pulito architetturalmente e riusabile da osc, ma aggiunge codice API,
  test e un'altra cosa da verificare sulla VM. Scartato: più lavoro e più
  superficie di rischio per un progetto già completo; si può promuovere ad A→B
  in futuro.
- **C — Solo fascia riassuntiva in cima alle Scansioni.** Minimo sforzo, ma
  niente "dashboard pulita" e poco visibile. Scartato: non centra l'obiettivo.

UUID→nomi: scelto il **pragmatico** (nomi dove presenti + UUID accorciato con
tooltip), non la risoluzione via Keystone/Neutron nelle tabelle, per non
aggiungere chiamate che possono fallire.

## Come è fatto (decisioni prese)

### 1. Modulo etichette condiviso — `recon_stack/dashboard/recon/labels.py` (nuovo)

Un unico posto per le traduzioni e i colori, riusato da tabelle, template e
Riepilogo. Contiene dizionari e funzioni pure (testabili sul Mac, nessun import
Horizon):

- `SEVERITY_LABELS`: high→"Grave", medium→"Media", low→"Bassa", info→"Informativa".
- `SEVERITY_CSS`: high→"danger", medium→"warning", low→"info", info→"default"
  (classi badge Bootstrap che Horizon già usa).
- `FINDING_LABELS`: per tutti e **8** i tipi, es. overexposed→"Esposto a
  chiunque", latent_service→"Servizio non previsto", useless_rule→"Regola
  inutile", unknown_exposed→"Host sconosciuto esposto", externally_reachable→
  "Raggiungibile da fuori", wasted_floating_ip→"Floating IP sprecato",
  external_only→"Visto solo da fuori", no_port_security→"Senza port security".
  (Testi definitivi rifiniti in implementazione, concordati col glossario.)
- `STATUS_LABELS`: RUNNING→"In corso", DONE→"Completata", FAILED→"Fallita",
  PENDING→"In attesa".
- `TRIGGER_LABELS`: manual→"Manuale", periodic→"Periodica", api→"API" (valori
  reali confermati dai costanti SCAN_*/TRIGGER_* in implementazione).
- Helper: `short_uuid(value)` → primi 8 caratteri + "…"; `severity_label`,
  `severity_css`, `finding_label`, `status_label`, `trigger_label` con fallback
  al valore grezzo se sconosciuto.

I costanti grezzi restano in `db/models.py`; `labels.py` mappa solo per la
vista.

### 2. Nuovo pannello Riepilogo — `recon_stack/dashboard/recon/overview/`

- `panel.py` (classe `Overview`, slug "overview"), `urls.py`, `views.py`
  (`generic.TemplateView`), `templates/overview/index.html`.
- `dashboard.py`: `panels = ("overview", "hosts", "services", "scans")` e
  `default_panel = "overview"`.
- La vista: `client = api.reconclient(request)`; prende l'ultima scansione DONE
  (`list_scans(status="DONE")`, prima), poi `get_scan_exposure(scan_id)`.
  Costruisce il contesto: scansione (stato/date leggibili), conteggi per
  gravità, e le prime N segnalazioni gravi. Ogni chiamata in try/except: se la
  API non risponde, la pagina mostra "nessuna scansione ancora" invece di
  rompersi.
- Template: poche "schede" in cima (card Bootstrap) — Ultima scansione (stato +
  quando), poi una riga di conteggi per gravità coi badge colorati, poi una
  tabellina "Da guardare subito" con le segnalazioni gravi (link al dettaglio
  scansione). Stile sobrio con le classi che Horizon già porta, niente CSS/JS
  nuovi se evitabile.

### 3. Pulizia dell'esistente

- `hosts/tables.py`, `services/tables.py`: le etichette già tradotte restano;
  dove compaiono UUID (network_id) si usa `short_uuid` con tooltip
  (`Column` con `filters` o una funzione di cella che ritorna testo accorciato;
  il valore pieno nel `title`/tooltip via template di cella se necessario).
- `scans/tables.py`: `status`→`status_label` con badge, `trigger`→
  `trigger_label`, `created_at`→data leggibile, `id`/`project_id` accorciati.
- `scans/templates/scans/detail.html`: gravità come badge colorato
  (`severity_label`+`severity_css`), tipo come `finding_label`, date leggibili,
  UUID accorciati con tooltip.
- `hosts/templates/hosts/detail.html`: classificazione già tradotta nella
  tabella; nel dettaglio applicare la stessa etichetta e accorciare gli UUID.
- Date leggibili: filtro template Django `|date:"d M Y H:i"` dove il valore è
  una data; nelle tabelle, funzione di cella che formatta la stringa ISO.

### 4. Avvia scansione con elenco progetti — `scans/forms.py`

- `StartScanForm.__init__`: prova a popolare un `ChoiceField` con i progetti da
  Keystone (import pigro `openstack_dashboard.api.keystone.tenant_list`). Se
  fallisce o l'elenco è vuoto, ripiega sul `CharField` attuale (incolla UUID).
  `handle()` invariato (POST /v1/scans con l'id scelto).

## Test

- Unit sul Mac per `labels.py` (funzioni pure: tutte le mappe + fallback +
  `short_uuid`).
- La vista Riepilogo con un client finto (come i test esistenti di
  `dashboard/api.py`) per verificare il contesto (conteggi, degrado con grazia
  se la API solleva).
- `recon/**` (template, form con Keystone) verificati sulla VM come il resto del
  pannello (horizon/django non installati sul Mac).

## Verifica finale (VM DevStack)

In coda, insieme alla prossima demo: Riepilogo mostra l'ultima scansione e i
conteggi giusti; badge colorati corretti; date leggibili; dropdown progetti
funziona (e ripiega se Keystone non risponde); nessuna regressione sui pannelli
esistenti. Le 7 segnalazioni attese restano quelle (vedi appunti demo).

## Lasciato al costruttore

- Testi italiani definitivi delle etichette (coerenti col GLOSSARY).
- Numero N di segnalazioni gravi mostrate nel Riepilogo (proposta: 5).
- Dettaglio tecnico del tooltip UUID (filtro vs template di cella) secondo cosa
  è più pulito in Horizon.
- Conferma dell'ordine di `list_scans` e, se serve, ordinamento esplicito per
  `created_at`.
- Scelta se aggiornare `docs/architettura`/`CLAUDE.md`/README con la sezione
  dashboard (coerente con le abitudini del progetto).
