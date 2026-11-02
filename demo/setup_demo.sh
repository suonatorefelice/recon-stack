#!/usr/bin/env bash
#
# Crea un progetto OpenStack di prova da usare come bersaglio delle scansioni,
# in laboratorio, su DevStack (docs/piano.md, step 4).
#
# Che cosa crea, tutto dentro un progetto chiamato "recon-demo":
#   - un utente "recon-demo-user" (ruolo member nel progetto);
#   - una rete privata con una subnet (10.10.10.0/24);
#   - un router che collega la rete privata alla rete esterna "public";
#   - un security group che apre SSH e il ping, più due regole volutamente
#     sbagliate (porte aperte senza servizio dietro) per provare lo step 11, e
#     la "regola dello scanner" che apre le porte al solo indirizzo da cui parte
#     la scansione (ADR 0012);
#   - due VM (immagine cirros, la mini-immagine di prova di DevStack):
#       recon-demo-web  SSH, più un servizio sulla porta 9090 che il security
#                       group non apre: un servizio LATENTE;
#       recon-demo-db   SSH, più un secondo indirizzo (10.10.10.250) che
#                       Neutron non conosce, e la port security disattivata:
#                       un HOST SCONOSCIUTO su una porta SENZA FIREWALL;
#   - un floating IP associato alla prima VM.
#
# I programmi dentro le VM partono da soli all'avvio: li passiamo come
# "user-data", uno script che cirros esegue al primo avvio. Così non serve
# entrare nelle VM.
#
# Serve a provare lo Step 4: l'inventario raccolto dal servizio deve coincidere
# con "openstack server list", "port list" e "floating ip list" su questo
# progetto. Le scansioni vere si eseguono SOLO su questo progetto (CLAUDE.md).
#
# USO (sul nodo DevStack, dopo aver caricato le credenziali admin):
#   source /opt/stack/devstack/openrc admin admin   # imposta OS_AUTH_URL ecc.
#   bash demo/setup_demo.sh
#
# Lo script è ripetibile: se una risorsa esiste già, la riusa invece di
# duplicarla. Per progetto e utente c'è l'opzione --or-show di Keystone; per
# reti, subnet, router e security group (Neutron) quell'opzione non esiste, e
# controlliamo a mano con la funzione exists_in_project.

# -e: esce al primo errore; -u: errore se si usa una variabile non impostata;
# -o pipefail: un errore in mezzo a una pipe non passa inosservato.
set -euo pipefail

# --- Nomi delle risorse (tutte con il prefisso recon-demo) -------------------
PROJECT=recon-demo
USER_NAME=recon-demo-user
USER_PASS=recon-demo
NET=recon-demo-net
SUBNET=recon-demo-subnet
SUBNET_RANGE=10.10.10.0/24
ROUTER=recon-demo-router
SECGROUP=recon-demo-sg
EXTERNAL_NET=public          # la rete esterna standard di DevStack
IMAGE_HINT=cirros            # pezzo del nome dell'immagine di prova
SERVERS=(recon-demo-web recon-demo-db)
# La subnet assegna indirizzi solo fino a .200: così UNKNOWN_IP non verrà mai
# dato a una porta Neutron e resta davvero "sconosciuto".
POOL_START=10.10.10.2
POOL_END=10.10.10.200
UNKNOWN_IP=10.10.10.250
LATENT_PORT=9090
# RAM minima del flavor delle VM. Su x86 cirros parte anche con 128 MB, ma su
# ARM (aarch64) si avvia tramite UEFI e GRUB: nel primo test su DevStack con
# Mac M1, con 192 MB GRUB si fermava con "error: out of memory" e con 256 MB il
# firmware andava in "Synchronous Exception" caricando il kernel; con 512 MB
# cirros arriva al login in circa 100 secondi.
MIN_RAM_MB=512

# Controlliamo che le credenziali admin siano caricate: senza OS_AUTH_URL non
# possiamo poi autenticarci come l'utente demo per creare le VM.
if [[ -z "${OS_AUTH_URL:-}" ]]; then
  echo "ERRORE: carica prima le credenziali admin, es.:" >&2
  echo "  source /opt/stack/devstack/openrc admin admin" >&2
  exit 1
fi

# Vero se nel progetto demo esiste già una risorsa Neutron con quel nome.
# Uso: exists_in_project <tipo> <nome>, es. exists_in_project network recon-demo-net
# Filtriamo per progetto perché l'admin vede le risorse di tutti i progetti.
exists_in_project() {
  # $1 senza virgolette apposta: "security group" deve diventare due parole.
  openstack $1 list --project "$PROJECT" -f value -c Name | grep -qx "$2"
}

echo "== 1/7 progetto, utente e ruoli =="
# --or-show: se esiste già, mostra quella esistente invece di dare errore.
openstack project create --or-show "$PROJECT" >/dev/null
openstack user create --or-show --project "$PROJECT" \
  --password "$USER_PASS" "$USER_NAME" >/dev/null
# Diamo all'utente il ruolo "member" nel progetto demo (idempotente).
openstack role add --project "$PROJECT" --user "$USER_NAME" member || true

echo "== 2/7 rete e subnet =="
exists_in_project network "$NET" ||
  openstack network create --project "$PROJECT" "$NET" >/dev/null
exists_in_project subnet "$SUBNET" ||
  openstack subnet create --project "$PROJECT" \
    --network "$NET" --subnet-range "$SUBNET_RANGE" \
    --allocation-pool "start=$POOL_START,end=$POOL_END" "$SUBNET" >/dev/null

echo "== 3/7 router verso la rete esterna '$EXTERNAL_NET' =="
exists_in_project router "$ROUTER" ||
  openstack router create --project "$PROJECT" "$ROUTER" >/dev/null
# Collega il router alla rete esterna (gateway) e alla subnet privata.
# "|| true" perché ripetere questi comandi su un router già collegato dà errore.
openstack router set --external-gateway "$EXTERNAL_NET" "$ROUTER" || true
openstack router add subnet "$ROUTER" "$SUBNET" 2>/dev/null || true

echo "== 4/7 security group (SSH e ping, più due regole volutamente sbagliate) =="
exists_in_project "security group" "$SECGROUP" ||
  openstack security group create --project "$PROJECT" "$SECGROUP" >/dev/null
# Regole in ingresso: TCP 22 (SSH) e ICMP (ping) da qualunque indirizzo.
# "|| true" perché ricreare una regola uguale dà errore.
# La 22 da 0.0.0.0/0 è una vera esposizione: cirros ha SSH in ascolto, quindi
# lo step 11 la segnala come "esposizione eccessiva".
openstack security group rule create --project "$PROJECT" \
  --proto tcp --dst-port 22 "$SECGROUP" >/dev/null 2>&1 || true
openstack security group rule create --project "$PROJECT" \
  --proto icmp "$SECGROUP" >/dev/null 2>&1 || true

# Due regole SBAGLIATE DI PROPOSITO, per far vedere lo step 11 al lavoro:
#   - TCP 3306 (MySQL) da qualunque indirizzo: su cirros non c'è nessun MySQL in
#     ascolto, quindi è una "regola inutile" (apre una porta senza servizio);
#   - TCP 8080 da qualunque indirizzo: anche questa senza servizio dietro.
# Non sono errori dello script: servono alla verifica ("le regole volutamente
# sbagliate del progetto demo vengono segnalate", docs/piano.md step 11).
openstack security group rule create --project "$PROJECT" \
  --proto tcp --dst-port 3306 "$SECGROUP" >/dev/null 2>&1 || true
openstack security group rule create --project "$PROJECT" \
  --proto tcp --dst-port 8080 "$SECGROUP" >/dev/null 2>&1 || true

# La regola dello scanner (ADR 0012): apre tutte le porte TCP al SOLO indirizzo
# da cui parte la scansione interna, cioè la porta dei metadati di OVN
# (network:distributed) o, con OVS, quella del DHCP (network:dhcp). Senza
# questa regola il security group blocca anche lo scanner e i servizi latenti
# restano invisibili. Recon-Stack la riconosce e non la conta come regola che
# "prevede" un servizio.
SCANNER_IP=""
for owner in network:distributed network:dhcp; do
  SCANNER_IP=$(openstack port list --network "$NET" --device-owner "$owner" \
               -f value -c "Fixed IP Addresses" \
               | grep -o -E "[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+" | head -1 || true)
  [[ -n "$SCANNER_IP" ]] && break
done
if [[ -n "$SCANNER_IP" ]]; then
  echo "   regola dello scanner: tutte le porte TCP da $SCANNER_IP/32"
  openstack security group rule create --project "$PROJECT" \
    --proto tcp --dst-port 1:65535 --remote-ip "$SCANNER_IP/32" \
    "$SECGROUP" >/dev/null 2>&1 || true
else
  echo "   ATTENZIONE: porta dei metadati/DHCP non trovata, niente regola dello scanner"
fi

# --- Da qui creiamo le VM come l'utente demo, nel progetto demo --------------
# "openstack server create" crea la VM nel progetto con cui ci si autentica:
# quindi ci autentichiamo come recon-demo-user nel progetto recon-demo,
# riusando OS_AUTH_URL delle credenziali admin già caricate.
AS_DEMO=(--os-auth-url "$OS_AUTH_URL"
         --os-project-name "$PROJECT"
         --os-username "$USER_NAME"
         --os-password "$USER_PASS"
         --os-user-domain-name "${OS_USER_DOMAIN_NAME:-Default}"
         --os-project-domain-name "${OS_PROJECT_DOMAIN_NAME:-Default}")

echo "== 5/7 due VM nel progetto demo =="
# Gli script di avvio (user-data) delle due VM.
USERDATA_DIR=$(mktemp -d)
trap 'rm -rf "$USERDATA_DIR"' EXIT
cat > "$USERDATA_DIR/recon-demo-web" <<UD
#!/bin/sh
# Servizio di prova sulla porta $LATENT_PORT, che il security group non apre:
# Recon-Stack lo deve segnalare come servizio latente.
( while true; do echo recon-demo | nc -l -p $LATENT_PORT; done ) &
UD
cat > "$USERDATA_DIR/recon-demo-db" <<UD
#!/bin/sh
# Secondo indirizzo che Neutron non conosce: Recon-Stack lo deve segnalare come
# host sconosciuto.
ip addr add $UNKNOWN_IP/24 dev eth0
UD
# Troviamo l'immagine cirros e il flavor più piccolo disponibili.
IMAGE=$(openstack image list -f value -c Name | grep -i "$IMAGE_HINT" | head -1)
if [[ -z "$IMAGE" ]]; then
  echo "ERRORE: nessuna immagine '$IMAGE_HINT' trovata su questo DevStack." >&2
  exit 1
fi
# Il flavor più piccolo con almeno MIN_RAM_MB di memoria.
FLAVOR=$(openstack flavor list -f value -c Name -c RAM \
         | awk -v min="$MIN_RAM_MB" '$2 >= min' | sort -k2 -n | head -1 | awk '{print $1}')
if [[ -z "$FLAVOR" ]]; then
  echo "ERRORE: nessun flavor con almeno $MIN_RAM_MB MB di RAM." >&2
  exit 1
fi
echo "   immagine: $IMAGE   flavor: $FLAVOR"

for name in "${SERVERS[@]}"; do
  if openstack "${AS_DEMO[@]}" server show "$name" >/dev/null 2>&1; then
    echo "   $name esiste già"
  else
    echo "   creo $name"
    openstack "${AS_DEMO[@]}" server create \
      --image "$IMAGE" --flavor "$FLAVOR" \
      --network "$NET" --security-group "$SECGROUP" \
      --user-data "$USERDATA_DIR/$name" \
      --wait "$name" >/dev/null
  fi
done

echo "== 6/7 floating IP sulla prima VM =="
FIRST="${SERVERS[0]}"
# Creiamo un floating IP sulla rete esterna e lo associamo alla prima VM, se
# non ne ha già uno.
if openstack "${AS_DEMO[@]}" floating ip list --port \
     "$(openstack "${AS_DEMO[@]}" port list --server "$FIRST" -f value -c ID | head -1)" \
     -f value -c "Floating IP Address" 2>/dev/null | grep -q .; then
  echo "   $FIRST ha già un floating IP"
else
  FIP=$(openstack "${AS_DEMO[@]}" floating ip create "$EXTERNAL_NET" \
        -f value -c floating_ip_address)
  openstack "${AS_DEMO[@]}" server add floating ip "$FIRST" "$FIP"
  echo "   $FIRST -> $FIP"
fi

echo "== 7/7 port security disattivata su recon-demo-db =="
# Senza port security OVN lascia passare anche UNKNOWN_IP, che non appartiene a
# nessuna porta. È anche il caso "porta senza firewall": nessun security group
# protegge la VM. Bisogna togliere i security group prima di disattivarla.
DB_PORT=$(openstack "${AS_DEMO[@]}" port list --server "${SERVERS[1]}" -f value -c ID | head -1)
openstack port set --no-security-group --disable-port-security "$DB_PORT"
echo "   porta $DB_PORT: port security disattivata"

echo
echo "Progetto demo pronto. Per vedere cosa dovrebbe trovare la scansione:"
echo "  openstack server list      --project $PROJECT"
echo "  openstack port list        --project $PROJECT"
echo "  openstack floating ip list --project $PROJECT"
echo "Le VM impiegano qualche minuto ad avviarsi (su ARM circa 2): scansiona dopo."
