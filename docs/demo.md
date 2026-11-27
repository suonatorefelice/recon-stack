# La demo di Recon-Stack

Come **preparare ed eseguire** la demo dal vivo, e **cosa** crea il bersaglio
(il progetto `recon-demo`) e **perché** ogni pezzo fa scattare una segnalazione.

Il bersaglio non fa parte di Recon-Stack: è lo scenario di laboratorio,
costruito apposta perché una scansione trovi tutti i casi interessanti (host
sconosciuti, servizi latenti, regole di firewall inutili, porte esposte). Tutte
le scansioni girano **solo** su questo progetto.

## Indirizzi e credenziali

| Cosa | Valore |
| --- | --- |
| Dashboard (Horizon) | **http://192.168.97.128/dashboard** |
| Login | utente `admin`, password `ADMIN_PASSWORD` del `local.conf` (nel laboratorio `admin`), dominio `Default` |
| VM di laboratorio (SSH) | `ssh -i ~/.ssh/vm_lab suqalo@192.168.97.128` |

La dashboard "Recon-Stack" è **solo per admin**.

---

## Parte 1 — Preparazione (da terminale, una volta sola)

Serve all'inizio, o quando il Mac/la VM sono stati spenti. Se la VM è già accesa
e la demo è stata preparata di recente, **salta alla Parte 2**.

### 1. Accendi la VM di laboratorio

```console
$ "/Applications/VMware Fusion.app/Contents/Library/vmrun" start \
    "/Users/pasquale/Virtual Machines.localized/Ubuntu.vmwarevm/Ubuntu.vmx" nogui
```

Su questo Mac (ARM) l'avvio può richiedere **più di 2 minuti** e il comando
sembra "appeso": è normale, aspetta (interromperlo spegne la VM). È pronta
quando risponde l'SSH: `ssh -i ~/.ssh/vm_lab suqalo@192.168.97.128 'echo ok'`.

### 2. Rimetti su la rete esterna (`br-ex`)

**Dopo ogni avvio a freddo** il bridge della rete esterna resta spento: i
floating IP non rispondono e `externally_reachable` non comparirebbe.

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

Alla fine le due VM devono risultare **ACTIVE** e `recon-demo-web` avere un
floating IP (`172.24.4.x`).

> **Aspetta ~2 minuti** prima di scansionare: le cirros devono finire di
> avviarsi e far partire i servizi (cloud-init), altrimenti la scansione vede
> meno di 7 segnalazioni.

---

## Parte 2 — La demo (dalla dashboard)

### 1. Entra nella dashboard

Apri **http://192.168.97.128/dashboard**, accedi come `admin` / `admin`
(dominio `Default`). Nella barra laterale compare la dashboard **«Recon-Stack»**
con i pannelli **Riepilogo** (la pagina iniziale), **Host**, **Servizi**,
**Scansioni**.

### 2. Lancia una scansione

1. Apri il pannello **Scansioni**.
2. In alto a destra, premi **«Avvia scansione»**.
3. Scegli il progetto dall'elenco a tendina e conferma. L'elenco mostra solo
   `recon-demo`: i progetti scansionabili li fissa l'impostazione di Horizon
   `RECON_SCANNABLE_PROJECTS` (predefinita `("recon-demo",)`); se nessun
   progetto combacia, il menu li mostra tutti.

La riga si aggiorna **da sola**: lo stato passa a *In corso* e la colonna
**«Fase»** avanza ("Scoperta host e servizi (3 di 6)" ecc.). Nel **dettaglio**
c'è la rotella e la pagina si aggiorna finché non è **Completata** (circa un
minuto); poi l'auto-aggiornamento si ferma da solo.

### 3. Mostra il Riepilogo

Apri **Riepilogo**: i conteggi per gravità con i badge colorati (**Grave 3 ·
Media 1 · Bassa 2 · Informativa 1**) e la tabella **«Da guardare subito»** con
le 5 segnalazioni più gravi, a partire dalle 3 gravi. Sono le **7 segnalazioni** attese (vedi la tabella più sotto).

### 4. Racconta i dettagli (facoltativo)

- **Host**: `10.10.10.250` classificato *sconosciuto* (risponde ma nessuna porta Neutron lo spiega), le due VM *censite*; aprendo un host vedi i suoi servizi.
- **Servizi**: la ricerca per nome (es. `ssh`), con porta e versione.
- **Dettaglio scansione**: le segnalazioni di esposizione e il **diff** rispetto alla scansione precedente (serve una seconda scansione dello stesso progetto, almeno 60 secondi dopo la prima: è il limite di frequenza `[scanner] min_scan_interval`).

### 5. Il report (facoltativo)

Il report di una scansione (tabelle di scansione, esposizione, host e servizi) è
una pagina stampabile della dashboard: nel pannello **Scansioni**, sulla riga di
una scansione *completata*, il pulsante «Report» apre la pagina, che si stampa
dal browser (anche come PDF). È costruita dalle stesse rotte `/v1` dei pannelli,
quindi non serve alcun comando dal terminale.

---

## Cosa crea il bersaglio e perché

Lo script `demo/setup_demo.sh` è **idempotente** (se una risorsa esiste già la
riusa) e pretende le credenziali admin. Tutte le risorse hanno il prefisso
`recon-demo`. Valori chiave:

| Variabile | Valore | A cosa serve |
| --- | --- | --- |
| `SUBNET_RANGE` | `10.10.10.0/24` | la rete privata del progetto |
| `POOL_START`–`POOL_END` | `10.10.10.2`–`10.10.10.200` | gli indirizzi che Neutron può assegnare |
| `UNKNOWN_IP` | `10.10.10.250` | indirizzo **fuori** dal pool: Neutron non lo darà mai a una porta, così resta "sconosciuto" |
| `LATENT_PORT` | `9090` | la porta del servizio latente |
| `MIN_RAM_MB` | `512` | su ARM (Mac M1) cirros sotto i 512 MB non si avvia |

I 7 passi dello script:

1. **Progetto, utente e ruoli** — `recon-demo` + utente `recon-demo-user` (le VM nascono come questo utente, dentro questo progetto).
2. **Rete e subnet** — `recon-demo-net` con subnet `10.10.10.0/24`, indirizzi solo da `.2` a `.200`.
3. **Router** — collega la subnet privata alla rete esterna `public` (serve ai floating IP).
4. **Security group** `recon-demo-sg` — un misto di regole giuste e sbagliate di proposito: SSH 22 da `0.0.0.0/0` (→ `overexposed`), TCP 3306 e 8080 senza servizio dietro (→ due `useless_rule`), e la **regola dello scanner** ([0012](adr/0012-regola-dello-scanner.md)) che apre tutte le porte TCP al solo indirizzo da cui parte la scansione (senza, il firewall bloccherebbe anche lo scanner e i servizi latenti resterebbero invisibili).
5. **Le due VM** (cirros, via `user-data`/cloud-init, senza entrarci): `recon-demo-web` avvia un servizio sulla **9090** che il firewall non apre (→ `latent_service`); `recon-demo-db` si auto-assegna il secondo indirizzo `10.10.10.250` fuori dal pool (→ `unknown_exposed`).
6. **Floating IP** sulla prima VM: l'SSH risponde anche da fuori (→ `externally_reachable`).
7. **Port security disattivata** su `recon-demo-db`: lascia passare l'indirizzo auto-assegnato e lascia la VM senza firewall (→ `no_port_security`).

### Le 7 segnalazioni attese

| Gravità | Segnalazione | Dove | Perché |
| --- | --- | --- | --- |
| 🔴 Grave | `overexposed` | `recon-demo-web`, SSH 22 | aperto a chiunque (`0.0.0.0/0`) |
| 🔴 Grave | `unknown_exposed` | `10.10.10.250` | host che risponde ma OpenStack non conosce |
| 🔴 Grave | `no_port_security` | `recon-demo-db` | porta senza firewall (port security disattivata) |
| 🟠 Media | `latent_service` | `recon-demo-web`, 9090 | servizio in ascolto non previsto da nessuna regola |
| 🟡 Bassa | `useless_rule` | porta 3306 | regola che apre una porta senza servizio dietro |
| 🟡 Bassa | `useless_rule` | porta 8080 | idem |
| ⚪ Info | `externally_reachable` | floating IP | SSH raggiungibile da "Internet" |

---

## Se qualcosa non torna

| Sintomo | Causa più probabile | Rimedio |
| --- | --- | --- |
| Meno di 7 segnalazioni, manca `externally_reachable` | `br-ex` spento dopo un riavvio a freddo | rifai la **Parte 1 punto 2** e riscansiona |
| Meno di 7 segnalazioni, mancano latente/sconosciuto | le VM non hanno finito di avviarsi, o i servizi non sono ripartiti | aspetta un paio di minuti; se persiste, rifai la **Parte 1 punto 3** (teardown+setup) |
| Al posto dell'elenco dei progetti c'è un campo «Id progetto» | Horizon non ha potuto leggere i progetti da Keystone | ricarica la pagina; in alternativa incolla l'id (`openstack project show recon-demo -f value -c id`) |
| «Scansione non avviata… riprovare fra N s» | limite di frequenza: una scansione per progetto ogni `min_scan_interval` secondi (60) | aspetta i secondi indicati e riprova |
| La dashboard non si apre | la VM non è accesa o i servizi non sono su | rifai la **Parte 1 punto 1**; controlla `systemctl is-active devstack@recon-api apache2` |

## Pulizia

`demo/teardown_demo.sh` cancella tutto il progetto demo (VM, floating IP, router,
rete, security group, utente, progetto), nell'ordine giusto. Per rifare la demo
da zero: `teardown_demo.sh`, poi `setup_demo.sh`. Il `teardown` **non** cancella
le scansioni dal database di Recon-Stack: restano come storico (il Riepilogo
mostra comunque l'ultima scansione).
