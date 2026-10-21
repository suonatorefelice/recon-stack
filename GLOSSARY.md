# Glossario

Termini usati nel codice, nei documenti e nei messaggi di commit. La colonna "proprietario" dice chi definisce il termine: dove il proprietario è un componente OpenStack, usiamo la sua definizione e non la cambiamo.

Per una spiegazione discorsiva dei componenti OpenStack vedi [docs/concetti.md](docs/concetti.md).

## Il dominio del servizio

| Termine | Significato | Proprietario |
| --- | --- | --- |
| **Perimetro** | l'insieme degli indirizzi che è lecito scansionare: le subnet Neutron di un progetto, e nient'altro ([0002](docs/adr/0002-perimetro-dalle-subnet-neutron.md)) | recon-stack |
| **Scansione** | un'esecuzione completa su un progetto: inventario, host discovery, service discovery, riconciliazione. Ha un autore, un inizio, una fine, un esito | recon-stack |
| **Inventario** | ciò che OpenStack **dichiara**: VM, porte, IP, floating IP, security group, letti dalle API | recon-stack |
| **Osservato** | ciò che la scansione **vede**: host che rispondono, porte aperte, servizi | recon-stack |
| **Host** | un indirizzo IP del perimetro, visto dall'inventario, dalla scansione o da entrambi | recon-stack |
| **Host censito** | host che risponde e ha una porta Neutron: sappiamo a quale VM appartiene | recon-stack |
| **Host sconosciuto** | host che risponde ma non ha nessuna porta Neutron: nessuno l'ha dichiarato | recon-stack |
| **Host assente** | host che ha una porta Neutron ma non risponde alla scansione | recon-stack |
| **Servizio** | un programma in ascolto su una porta di un host: porta, protocollo, nome, prodotto, versione (es. `22/tcp ssh OpenSSH 8.9p1`) | recon-stack |
| **Catalogo** | l'elenco dei servizi dell'ultima scansione, interrogabile per servizio, host, rete, versione | recon-stack |
| **Diff** | le differenze fra una scansione e la precedente: host e servizi comparsi, spariti, cambiati di versione | recon-stack |
| **Vista interna** | la scansione fatta dall'interno della rete del progetto, tramite un namespace di rete ([0003](docs/adr/0003-scansione-dai-namespace-di-rete.md)) | recon-stack |
| **Vista esterna** | la scansione dei floating IP fatta dalla rete `public`: ciò che vede chi sta fuori dal cloud | recon-stack |
| **Servizio esposto** | servizio raggiungibile dalla vista esterna | recon-stack |
| **Servizio latente** | servizio in ascolto ma bloccato dal security group: innocuo oggi, esposto il giorno in cui qualcuno apre la regola | recon-stack |
| **Regola inutile** | regola di security group che apre una porta su cui non c'è nessun servizio in ascolto: un buco pronto per il prossimo programma che userà quella porta | recon-stack |
| **Redaction** | la versione condivisibile del report, con indirizzi, nomi e identificativi sostituiti da pseudonimi coerenti | recon-stack |

## I componenti OpenStack e cosa ci prendiamo

| Termine | Significato | Dove lo usiamo |
| --- | --- | --- |
| **Keystone** | identità, progetti, ruoli; rilascia i token | autentica ogni richiesta alla API; il ruolo `admin` è necessario per avviare scansioni |
| **Token** | prova temporanea di identità allegata a ogni richiesta HTTP | arriva nell'intestazione `X-Auth-Token`; il servizio non lo conserva |
| **Progetto** | lo spazio a cui appartengono le risorse (detto anche *tenant*) | l'unità di scansione: si scansiona sempre un progetto alla volta |
| **Nova** | crea e gestisce le macchine virtuali | letto per l'inventario delle VM; mai in scrittura |
| **Neutron** | reti, subnet, porte, router, floating IP, security group | letto per l'inventario e per calcolare il perimetro; mai in scrittura |
| **Subnet** | intervallo di indirizzi di una rete, es. `10.0.0.0/24` | definisce il perimetro |
| **Porta** | la "presa di rete" di una VM (o di un router, o del DHCP): ha MAC e IP | serve a dire se un host è censito |
| **Floating IP** | indirizzo della rete `public` associato a una porta privata | obiettivo della vista esterna |
| **Security group** | il firewall di OpenStack: regole di ingresso e uscita applicate alle porte | confrontato con i servizi per trovare latenti e regole inutili |
| **Namespace di rete** | una "stanza" di rete separata sul nodo, con le sue interfacce e i suoi indirizzi; Neutron ne crea una per rete | da lì si lancia nmap per la vista interna |
| **OVN / OVS** | i due modi con cui Neutron realizza le reti virtuali. OVN è il predefinito nelle versioni recenti di DevStack | decide il nome dei namespace: `ovnmeta-<id rete>` con OVN, `qdhcp-<id rete>` con OVS |
| **DevStack** | installazione di OpenStack da sorgenti su una sola macchina, per sviluppo, estendibile con plugin | l'ambiente in cui il servizio viene installato e provato |
| **Plugin DevStack** | repository con una cartella `devstack/` che DevStack scarica e chiama durante l'installazione | è il modo in cui il servizio si installa |

## Conflitti di terminologia da non creare

**Servizio** ha due significati. Per OpenStack un servizio è un componente del cloud (Nova, Neutron, il nostro `recon-api`), registrato nel catalogo di Keystone. Per noi un servizio è un programma in ascolto su una porta di un host. Nel codice: `Service` è sempre il secondo; il primo si chiama "componente" o con il suo nome.

**Porta** ha due significati. La porta Neutron è la presa di rete di una VM; la porta TCP/UDP è il numero su cui ascolta un servizio. Nel codice: `neutron_port` per la prima, `port_number` per la seconda.

**Host** per noi è un indirizzo IP, non un nodo di calcolo. Il nodo che esegue le VM si chiama "nodo" o "hypervisor".
