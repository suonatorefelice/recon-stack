# Guida alla demo dal vivo (dalla dashboard)

Questa è la guida operativa per **fare la demo di Recon-Stack davanti a qualcuno**,
usando il più possibile la **dashboard** e il minimo indispensabile di terminale.

L'idea è semplice: c'è una piccola **preparazione** che va per forza fatta da
terminale (accendere la VM di laboratorio e preparare il "bersaglio" da
scansionare — la dashboard non può accendere macchine virtuali né lanciare
script di shell), e poi **tutta la demo vera e propria si fa dal browser**:
lanciare la scansione, vedere le fasi che avanzano, leggere le segnalazioni.

> Per capire *cosa* crea il bersaglio e *perché* ogni pezzo fa scattare una
> segnalazione, vedi [demo.md](demo.md). Qui ci concentriamo sul **come fare la
> demo**.

---

## Indirizzi e credenziali

| Cosa | Valore |
| --- | --- |
| Dashboard (Horizon) | **http://192.168.97.128/dashboard** |
| Login | utente `admin`, password `admin`, dominio `Default` |
| VM di laboratorio (SSH) | `ssh -i ~/.ssh/vm_lab suqalo@192.168.97.128` |

La dashboard "Recon-Stack" è **solo per admin**: entra con `admin`.

---

## Parte 1 — Preparazione (da terminale, una volta sola)

Serve solo all'inizio, o quando il Mac/la VM sono stati spenti. Se la VM è già
accesa e la demo è già stata preparata di recente, **salta alla Parte 2**.

### 1. Accendi la VM di laboratorio

Dal Mac:

```console
$ "/Applications/VMware Fusion.app/Contents/Library/vmrun" start \
    "/Users/pasquale/Virtual Machines.localized/Ubuntu.vmwarevm/Ubuntu.vmx" nogui
```

Su questo Mac (ARM) l'avvio può richiedere **più di 2 minuti** e il comando
sembra "appeso": è normale, aspetta. Non interromperlo (interromperlo spegne la
VM). È pronta quando risponde l'SSH:

```console
$ ssh -i ~/.ssh/vm_lab suqalo@192.168.97.128 'echo ok'
```

### 2. Rimetti su la rete esterna (`br-ex`)

**Dopo ogni avvio a freddo** il bridge della rete esterna resta spento: i
floating IP non rispondono e la segnalazione `externally_reachable` non
comparirebbe. Rimettilo su (una riga, via SSH):

```console
$ ssh -i ~/.ssh/vm_lab suqalo@192.168.97.128 \
    'sudo ip link set br-ex up; sudo ip addr add 172.24.4.1/24 dev br-ex 2>/dev/null; true'
```

### 3. Prepara il bersaglio (progetto `recon-demo`)

Dopo un riavvio le VM della demo sono spente e **i loro servizi non ripartono da
soli** (un semplice "avvia" non rilancia cloud-init). Per riavere tutti e 7 i
casi, ricrea il bersaglio da zero: prima `teardown`, poi `setup`.

```console
$ ssh -i ~/.ssh/vm_lab suqalo@192.168.97.128 \
    'sudo -u stack bash -lc "
       cd /opt/stack/devstack && source openrc admin admin >/dev/null 2>&1
       cd /opt/stack/recon-stack
       bash demo/teardown_demo.sh
       bash demo/setup_demo.sh
       openstack server list --project recon-demo -c Name -c Status -c Networks"'
```

Alla fine le due VM devono risultare **ACTIVE** e `recon-demo-web` avere anche un
floating IP (`172.24.4.x`).

> **Aspetta ~2 minuti** prima di scansionare: le cirros devono finire di
> avviarsi e far partire i servizi (cloud-init), altrimenti la scansione vede
> meno di 7 segnalazioni. Segnale che la rete delle VM è su: il floating IP
> risponde al `ping` dalla VM di laboratorio.

Da qui in poi **si fa tutto dal browser**.

---

## Parte 2 — La demo (dalla dashboard)

### 1. Entra nella dashboard

Apri **http://192.168.97.128/dashboard**, accedi come `admin` / `admin`
(dominio `Default`). Nella barra laterale a sinistra compare la dashboard
**«Recon-Stack»** con i pannelli:

- **Riepilogo** — la pagina iniziale, il colpo d'occhio;
- **Host** — gli host trovati e come sono classificati;
- **Servizi** — i servizi in ascolto (porta, nome, versione);
- **Scansioni** — lo storico e il pulsante per avviarne una.

### 2. Lancia una scansione

1. Apri il pannello **Scansioni**.
2. In alto a destra, premi **«Avvia scansione»**.
3. Nel modulo scegli il progetto dall'elenco a tendina e conferma. Il menu
   mostra **solo `recon-demo`**: è l'unico progetto che si scansiona (gli altri
   sono progetti di sistema di OpenStack e non vanno toccati).

La scansione parte. Nell'elenco la riga si aggiorna **da sola** (non serve
ricaricare): vedrai lo stato passare a *In corso* e la colonna **«Fase»**
avanzare — "Scoperta host e servizi (3 di 6)" e così via. Entrando nel
**dettaglio** della scansione c'è la rotella che gira e la pagina si aggiorna da
sola finché non è **Conclusa**.

> Dura circa **un minuto**. Quando è *Conclusa*, l'auto-aggiornamento si ferma da
> solo.

### 3. Mostra il Riepilogo

Apri **Riepilogo**. Con la demo preparata bene vedrai:

- i conteggi per gravità, con i badge colorati: **Grave 3 · Media 1 · Bassa 2 ·
  Info 1**;
- la tabella **«Da guardare subito»** con le tre segnalazioni gravi in evidenza.

Sono le **7 segnalazioni** attese:

| Gravità | Segnalazione | Dove | Perché |
| --- | --- | --- | --- |
| 🔴 Grave | `no_port_security` | `recon-demo-db` | porta senza firewall (port security disattivata) |
| 🔴 Grave | `overexposed` | `recon-demo-web`, SSH 22 | aperto a chiunque (`0.0.0.0/0`) |
| 🔴 Grave | `unknown_exposed` | `10.10.10.250` | host che risponde ma OpenStack non conosce |
| 🟠 Media | `latent_service` | `recon-demo-web`, 9090 | servizio in ascolto non previsto da nessuna regola |
| 🟡 Bassa | `useless_rule` | porta 3306 | regola che apre una porta senza servizio dietro |
| 🟡 Bassa | `useless_rule` | porta 8080 | idem |
| ⚪ Info | `externally_reachable` | floating IP | SSH raggiungibile da "Internet" |

### 4. Racconta i dettagli (facoltativo)

- **Host**: fai vedere `recon-demo-db` classificato *sconosciuto* e gli altri
  *censiti*. Aprendo un host vedi i suoi servizi.
- **Servizi**: la ricerca per nome (es. `ssh`), con porta e versione.
- **Dettaglio scansione**: oltre alle segnalazioni di esposizione, c'è il
  **diff** rispetto alla scansione precedente (host/servizi comparsi o spariti).

---

## Se qualcosa non torna

| Sintomo | Causa più probabile | Rimedio |
| --- | --- | --- |
| Meno di 7 segnalazioni, manca `externally_reachable` | `br-ex` spento dopo un riavvio a freddo | rifai la **Parte 1 punto 2** e riscansiona |
| Meno di 7 segnalazioni, mancano latente/sconosciuto | le VM non hanno finito di avviarsi, o i servizi non sono ripartiti | aspetta un paio di minuti; se persiste, rifai la **Parte 1 punto 3** (teardown+setup) |
| L'elenco a tendina dei progetti è vuoto | Keystone non ha risposto | ricarica la pagina; in alternativa incolla l'id del progetto nel campo |
| La dashboard non si apre | la VM non è accesa o i servizi non sono su | rifai la **Parte 1 punto 1**; controlla `systemctl is-active devstack@recon-api devstack@recon-scanner apache2` |

## Fare pulizia dello storico (facoltativo)

Il `teardown` **non** cancella le scansioni dal database di Recon-Stack (restano
come storico). Se prima di una demo vuoi che la dashboard mostri **solo** la
scansione nuova, puoi svuotare lo storico tenendo l'ultima — è un'operazione sul
database, chiedi aiuto se non sei sicuro. In alternativa, lascia pure lo storico:
il Riepilogo mostra comunque **l'ultima** scansione.
