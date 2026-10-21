# OpenStack e DevStack, spiegati da zero

Questo documento spiega i concetti che servono per capire Recon-Stack. Non è un manuale di OpenStack: copre solo quello che il progetto usa. I termini precisi sono nel [glossario](../GLOSSARY.md).

## 1. Cos'è OpenStack

Con un cloud pubblico (AWS, Google Cloud) si apre un sito, si chiede una macchina virtuale e dopo pochi secondi la si ha. **OpenStack è il software che permette di costruire un cloud così sui propri server.**

Non è un programma unico: è un insieme di **componenti** separati, ognuno con un compito, che si parlano tramite API HTTP. Quelli che ci interessano:

| Componente | Cosa fa | In parole povere |
| --- | --- | --- |
| **Keystone** | autenticazione e permessi | il portiere: chi sei, a che progetto appartieni, che ruolo hai |
| **Nova** | macchine virtuali | la fabbrica di computer |
| **Neutron** | reti, router, indirizzi, firewall | l'impianto di rete |
| **Glance** | immagini dei sistemi operativi | lo scaffale dei dischi di installazione |
| **Horizon** | interfaccia web | il cruscotto |

Recon-Stack **legge** da Nova e Neutron e **si fa autenticare** da Keystone. Non crea né modifica risorse.

## 2. I concetti di rete

- **Progetto** (o *tenant*): uno spazio isolato, come un appartamento in un condominio. Ha le sue VM e le sue reti e non vede quelle degli altri.
- **Rete**: uno switch virtuale a cui si attaccano le VM.
- **Subnet**: l'intervallo di indirizzi di una rete. `10.0.0.0/24` vuol dire "da 10.0.0.0 a 10.0.0.255".
- **Porta Neutron**: la presa di rete. Ogni VM collegata a una rete ha una porta con un MAC e un IP. Anche il router e il DHCP hanno porte. **Neutron conosce tutte le porte**: è così che sappiamo quali IP sono "dichiarati".
- **Router**: collega una rete privata alla rete esterna (`public`).
- **Floating IP**: le VM hanno indirizzi privati, invisibili da fuori. Un floating IP è un indirizzo della rete `public` che si aggancia a una VM per renderla raggiungibile dall'esterno, come un numero pubblico che inoltra le chiamate a un interno.
- **Security group**: **il firewall** di OpenStack. È una lista di regole come "lascia entrare TCP porta 22 da qualunque indirizzo", applicata alle porte delle VM. Ciò che non è permesso in ingresso viene scartato.

## 3. Cos'è DevStack

Installare OpenStack per davvero richiede più server e giorni di lavoro. **DevStack è uno script che installa tutto OpenStack su una sola macchina**, scaricandolo dai sorgenti. Serve a chi sviluppa, non per la produzione.

1. si scarica DevStack (`git clone https://opendev.org/openstack/devstack`);
2. si scrive `local.conf`, il file che dice cosa installare;
3. si lancia `./stack.sh`, che dopo 20-40 minuti lascia OpenStack acceso;
4. `./unstack.sh` lo spegne, `./clean.sh` lo rimuove.

Ogni componente gira come servizio di sistema (systemd) chiamato `devstack@<nome>`. Recon-Stack ne aggiunge due: `devstack@recon-api` e `devstack@recon-scanner`. Si controllano con `sudo systemctl status devstack@recon-api` e i loro log con `sudo journalctl -u devstack@recon-api`.

## 4. Cos'è un plugin DevStack

Un plugin dice a DevStack: "quando installi OpenStack, installa e avvia anche questo". Si abilita con una riga in `local.conf`:

```ini
enable_plugin recon-stack https://github.com/suonatorefelice/recon-stack main
```

DevStack allora:

1. scarica il repository in `/opt/stack/recon-stack`;
2. legge `devstack/settings`, la carta d'identità del plugin: nome, servizi da abilitare, variabili;
3. chiama `devstack/plugin.sh` più volte, passando due parole che dicono a che punto è l'installazione.

| Chiamata | Quando avviene | Cosa ci facciamo |
| --- | --- | --- |
| `stack install` | dopo aver installato i componenti | installiamo il pacchetto, nmap, graphviz e il wrapper |
| `stack post-config` | i componenti sono configurati, non ancora avviati | scriviamo la configurazione, creiamo il database, registriamo il servizio in Keystone |
| `stack extra` | OpenStack è acceso | avviamo `recon-api` e `recon-scanner` |
| `unstack` | `./unstack.sh` | fermiamo i processi |
| `clean` | `./clean.sh` | togliamo la configurazione |

Le funzioni usate dentro `plugin.sh` (`install_package`, `setup_develop`, `run_process`, `stop_process`, `iniset`, ...) sono **già fornite da DevStack**. Fonte: <https://docs.openstack.org/devstack/latest/plugins.html>

## 5. Come si parla con OpenStack da Python

La libreria **openstacksdk** fa le chiamate HTTP al posto nostro. Le credenziali sono in `/etc/openstack/clouds.yaml`, che DevStack scrive da solo; la voce `devstack-admin` accede come amministratore.

```python
import openstack

conn = openstack.connect(cloud="devstack-admin")   # login con clouds.yaml

for server in conn.compute.servers(all_projects=True):  # compute = Nova
    print(server.name, server.addresses)

for port in conn.network.ports(project_id=pid):          # network = Neutron
    print(port.fixed_ips, port.device_id)                # IP e VM a cui appartiene
```

## 6. nmap

**nmap** "bussa" agli indirizzi per vedere chi risponde e cosa offre.

- `nmap -sn 10.0.0.0/24`: chi è acceso nella subnet (**host discovery**, nessuna porta toccata).
- `nmap -sV 10.0.0.5`: quali porte sono aperte e quale programma, con che versione, risponde (**service discovery**).

nmap riporta ogni porta in uno di tre stati: `open` (c'è un servizio), `closed` (l'host risponde ma lì non c'è niente), `filtered` (nessuna risposta: un firewall ha scartato il pacchetto).

Scansionare reti altrui è illegale. Per questo Recon-Stack accetta solo indirizzi che Neutron dichiara appartenere al progetto.

## 7. I namespace di rete

Le reti private sono **isolate**: neanche il nodo che ospita OpenStack le raggiunge direttamente. Linux però permette di creare **namespace di rete**, "stanze" con interfacce e indirizzi propri. Neutron ne crea una collegata a ogni rete privata, per i suoi servizi interni (DHCP o metadati). Un programma lanciato **dentro** quella stanza vede la rete come la vedrebbe una VM.

```bash
sudo ip netns list                                      # elenca i namespace
sudo ip netns exec ovnmeta-<id-rete> ip addr            # che indirizzo ha la stanza
sudo ip netns exec ovnmeta-<id-rete> nmap -sn 10.0.0.0/24
```

Il nome dipende da come Neutron realizza le reti: `ovnmeta-<id rete>` con OVN (predefinito nelle versioni recenti), `qdhcp-<id rete>` con OVS. Entrare in un namespace richiede i privilegi di root.

## 8. Service discovery: due significati

"Service discovery" nei microservizi (Kubernetes, Docker) vuol dire che i servizi **si registrano** e si trovano per nome tramite un DNS interno: funziona perché l'orchestratore sa cosa gira in ogni container, glielo dichiara chi lo avvia. In OpenStack l'equivalente a livello di macchina è Designate, il DNS del cloud: dà un nome a ogni VM, ma non sa cosa gira dentro.

Recon-Stack fa l'altra cosa: **scopre** cosa gira davvero, senza che nessuno lo dichiari e senza installare niente nelle VM, e lo mette a confronto con ciò che OpenStack dichiara.
