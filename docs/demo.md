# Il progetto demo spiegato (`demo/setup_demo.sh`)

Questo documento spiega, riga per riga a grandi blocchi, **che cosa fa lo script
`demo/setup_demo.sh`** e **perché**. Serve a creare su DevStack un progetto di
prova — `recon-demo` — costruito apposta perché la scansione di Recon-Stack
trovi tutti i casi interessanti: host sconosciuti, servizi latenti, regole di
firewall inutili, porte esposte.

> In sintesi: lo script prepara il **bersaglio** delle scansioni. Non fa parte
> di Recon-Stack, è solo lo scenario di laboratorio su cui mostriamo che
> Recon-Stack funziona. Tutte le scansioni girano **solo** su questo progetto.

## Come si lancia

```console
$ source /opt/stack/devstack/openrc admin admin   # carica le credenziali admin
$ bash /opt/stack/recon-stack/demo/setup_demo.sh
```

Lo script **pretende** le credenziali admin: all'inizio controlla che la
variabile `OS_AUTH_URL` sia impostata (la imposta `openrc`) e, se manca, si
ferma con un errore. Gli serve perché deve creare progetti, utenti e reti, cose
che solo l'admin può fare.

Lo script è **ripetibile** (idempotente): se una risorsa esiste già, la riusa
invece di crearne una seconda. Così puoi rilanciarlo senza paura. Dove Keystone
lo permette usa l'opzione `--or-show` (se esiste, mostra quella che c'è); per le
risorse di rete, che non hanno quell'opzione, controlla a mano con la funzione
`exists_in_project`.

## I nomi e i numeri decisi all'inizio

Tutte le risorse hanno il prefisso `recon-demo`. I valori chiave:

| Variabile | Valore | A cosa serve |
| --- | --- | --- |
| `SUBNET_RANGE` | `10.10.10.0/24` | la rete privata del progetto |
| `POOL_START`–`POOL_END` | `10.10.10.2`–`10.10.10.200` | gli indirizzi che Neutron può assegnare |
| `UNKNOWN_IP` | `10.10.10.250` | un indirizzo **fuori** dal pool: Neutron non lo darà mai a una porta, così resta "sconosciuto" |
| `LATENT_PORT` | `9090` | la porta del servizio latente |
| `MIN_RAM_MB` | `512` | RAM minima della VM: su ARM (Mac M1) cirros sotto i 512 MB non si avvia (UEFI/GRUB vanno in *out of memory*) |

Il trucco dell'indirizzo sconosciuto sta tutto qui: il pool arriva solo fino a
`.200`, quindi `.250` non apparterrà mai a nessuna porta Neutron. Quando la VM se
lo auto‑assegnerà (vedi sotto), Recon-Stack vedrà un host che risponde ma che
OpenStack non conosce → **host sconosciuto**.

## I 7 passi dello script

### 1/7 — Progetto, utente e ruoli

Crea il progetto `recon-demo`, un utente `recon-demo-user` (password
`recon-demo`) e gli assegna il ruolo `member` nel progetto. L'utente serve dopo:
le VM verranno create **come questo utente dentro questo progetto**, non come
admin (una VM appartiene al progetto con cui ti autentichi).

### 2/7 — Rete e subnet

Crea una rete privata `recon-demo-net` con una subnet `10.10.10.0/24`, dicendo a
Neutron di assegnare indirizzi **solo** da `.2` a `.200` (l'`--allocation-pool`).
È la rete che la scansione interna esplorerà.

### 3/7 — Router verso la rete esterna

Crea un router `recon-demo-router`, lo collega alla rete esterna `public` (il
*gateway*, che dà l'uscita verso "l'esterno") e alla subnet privata. Serve
perché i floating IP (indirizzi "pubblici" di laboratorio) possano raggiungere
le VM.

### 4/7 — Security group: le regole del firewall

Il *security group* `recon-demo-sg` è il firewall delle VM. Lo script ci mette
dentro, di proposito, un misto di regole giuste e sbagliate, ognuna pensata per
far scattare una segnalazione:

- **TCP 22 (SSH) da `0.0.0.0/0`** e **ICMP (ping)**: regole normali. Ma cirros ha
  davvero SSH in ascolto, e aprirlo a *qualunque* indirizzo è una vera
  esposizione → segnalazione **`overexposed`** (high).
- **TCP 3306** e **TCP 8080 da `0.0.0.0/0`**: aprono due porte su cui **non c'è
  nessun servizio**. Sono sbagliate apposta → due segnalazioni **`useless_rule`**
  (low): "apri una porta che non serve, è superficie d'attacco inutile".
- **La "regola dello scanner"** (ADR 0012): apre *tutte* le porte TCP al **solo
  indirizzo da cui parte la scansione** — cioè la porta dei metadati di OVN
  (o del DHCP con OVS), che lo script trova da sé interrogando Neutron
  (`SCANNER_IP`). Senza questa regola, il firewall bloccherebbe anche lo scanner
  e i servizi latenti resterebbero invisibili. Recon-Stack la **riconosce** e non
  la conta come "una regola che prevede un servizio", così non falsa le altre
  segnalazioni.

### 5/7 — Le due VM

Crea due VM con l'immagine **cirros** (la mini‑immagine di prova di DevStack) e
il flavor più piccolo con almeno 512 MB di RAM. Le crea **come `recon-demo-user`**
(vedi l'array `AS_DEMO` con le credenziali dell'utente demo).

Il bello è che **non entriamo mai dentro le VM**: i programmi di prova partono da
soli all'avvio, perché li passiamo come **`user-data`**, uno script che cirros
esegue al primo avvio (è il meccanismo *cloud-init*).

- **`recon-demo-web`** — il suo user‑data avvia un servizio fittizio sulla porta
  **9090** (un `nc` in ascolto in un ciclo). Il security group **non** apre la
  9090 → è un **servizio latente**: è attivo ma nessuna regola lo prevede →
  segnalazione **`latent_service`** (medium).
- **`recon-demo-db`** — il suo user‑data aggiunge un **secondo indirizzo**
  `10.10.10.250` alla scheda di rete (`ip addr add ...`). Quell'indirizzo è fuori
  dal pool, quindi Neutron non lo conosce → **host sconosciuto** →
  segnalazione **`unknown_exposed`** (high).

> Per questo, dopo `setup_demo.sh`, bisogna aspettare ~2 minuti: le VM devono
> finire di avviarsi e `cloud-init` deve far partire i servizi, altrimenti la
> scansione non li vede ancora.

### 6/7 — Floating IP

Crea un floating IP sulla rete esterna e lo associa alla prima VM
(`recon-demo-web`), se non ne ha già uno. Dà alla VM un indirizzo "pubblico"
raggiungibile da fuori la rete privata. Siccome su quella VM l'SSH risponde anche
da fuori, Recon-Stack lo segnala come **`externally_reachable`** (info).

### 7/7 — Port security disattivata

Sulla porta di `recon-demo-db` toglie i security group e **disattiva la port
security**. Due effetti:

1. senza port security OVN lascia passare anche l'indirizzo `10.10.10.250` che la
   VM si è auto‑assegnato (altrimenti lo bloccherebbe perché non appartiene a
   nessuna porta);
2. è il caso **"porta senza firewall"**: nessun security group protegge più la
   VM → segnalazione **`no_port_security`** (high).

## Riepilogo: ogni pezzo della demo → la sua segnalazione

| Cosa crea lo script | Segnalazione attesa | Gravità |
| --- | --- | --- |
| SSH (22) aperto a `0.0.0.0/0` su `recon-demo-web` | `overexposed` | high |
| IP `10.10.10.250` auto‑assegnato da `recon-demo-db` | `unknown_exposed` | high |
| port security disattivata su `recon-demo-db` | `no_port_security` | high |
| servizio sulla 9090 non aperto dal firewall | `latent_service` | medium |
| regole 3306 e 8080 senza servizio dietro | `useless_rule` (×2) | low |
| SSH raggiungibile sul floating IP | `externally_reachable` | info |

In tutto **7 segnalazioni**. Se ne vedi meno, la causa più comune è che le VM non
hanno ancora finito di avviarsi, oppure (dopo un riavvio a freddo della VM
DevStack) che il bridge della rete esterna `br-ex` è spento e il floating IP non
risponde: vedi la sezione "Provarlo" del [README](../README.md).

## Fare pulizia

`demo/teardown_demo.sh` cancella tutto il progetto demo (VM, floating IP, router,
rete, security group, utente, progetto), nell'ordine giusto. Per rifare la demo
da zero: prima `teardown_demo.sh`, poi di nuovo `setup_demo.sh`.
