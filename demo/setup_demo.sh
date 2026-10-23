#!/usr/bin/env bash
#
# Crea un progetto OpenStack di prova da usare come bersaglio delle scansioni,
# in laboratorio, su DevStack (docs/piano.md, step 4).
#
# Che cosa crea, tutto dentro un progetto chiamato "recon-demo":
#   - un utente "recon-demo-user" (ruolo member nel progetto);
#   - una rete privata con una subnet (10.10.10.0/24);
#   - un router che collega la rete privata alla rete esterna "public";
#   - un security group che apre SSH e il ping;
#   - due VM (immagine cirros, la mini-immagine di prova di DevStack);
#   - un floating IP associato alla prima VM.
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
# duplicarla (opzione --or-show dei comandi "openstack ... create").

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

# Controlliamo che le credenziali admin siano caricate: senza OS_AUTH_URL non
# possiamo poi autenticarci come l'utente demo per creare le VM.
if [[ -z "${OS_AUTH_URL:-}" ]]; then
  echo "ERRORE: carica prima le credenziali admin, es.:" >&2
  echo "  source /opt/stack/devstack/openrc admin admin" >&2
  exit 1
fi

echo "== 1/6 progetto, utente e ruoli =="
# --or-show: se esiste già, mostra quella esistente invece di dare errore.
openstack project create --or-show "$PROJECT" >/dev/null
openstack user create --or-show --project "$PROJECT" \
  --password "$USER_PASS" "$USER_NAME" >/dev/null
# Diamo all'utente il ruolo "member" nel progetto demo (idempotente).
openstack role add --project "$PROJECT" --user "$USER_NAME" member || true

echo "== 2/6 rete e subnet =="
openstack network create --or-show --project "$PROJECT" "$NET" >/dev/null
openstack subnet create --or-show --project "$PROJECT" \
  --network "$NET" --subnet-range "$SUBNET_RANGE" "$SUBNET" >/dev/null

echo "== 3/6 router verso la rete esterna '$EXTERNAL_NET' =="
openstack router create --or-show --project "$PROJECT" "$ROUTER" >/dev/null
# Collega il router alla rete esterna (gateway) e alla subnet privata.
# "|| true" perché ripetere questi comandi su un router già collegato dà errore.
openstack router set --external-gateway "$EXTERNAL_NET" "$ROUTER" || true
openstack router add subnet "$ROUTER" "$SUBNET" 2>/dev/null || true

echo "== 4/6 security group (SSH e ping) =="
openstack security group create --or-show --project "$PROJECT" "$SECGROUP" >/dev/null
# Regole in ingresso: TCP 22 (SSH) e ICMP (ping) da qualunque indirizzo.
# "|| true" perché ricreare una regola uguale dà errore.
openstack security group rule create --project "$PROJECT" \
  --proto tcp --dst-port 22 "$SECGROUP" >/dev/null 2>&1 || true
openstack security group rule create --project "$PROJECT" \
  --proto icmp "$SECGROUP" >/dev/null 2>&1 || true

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

echo "== 5/6 due VM nel progetto demo =="
# Troviamo l'immagine cirros e il flavor più piccolo disponibili.
IMAGE=$(openstack image list -f value -c Name | grep -i "$IMAGE_HINT" | head -1)
if [[ -z "$IMAGE" ]]; then
  echo "ERRORE: nessuna immagine '$IMAGE_HINT' trovata su questo DevStack." >&2
  exit 1
fi
# Il flavor con meno RAM: cirros gira anche con pochissima memoria.
FLAVOR=$(openstack flavor list -f value -c Name -c RAM \
         | sort -k2 -n | head -1 | awk '{print $1}')
echo "   immagine: $IMAGE   flavor: $FLAVOR"

for name in "${SERVERS[@]}"; do
  if openstack "${AS_DEMO[@]}" server show "$name" >/dev/null 2>&1; then
    echo "   $name esiste già"
  else
    echo "   creo $name"
    openstack "${AS_DEMO[@]}" server create \
      --image "$IMAGE" --flavor "$FLAVOR" \
      --network "$NET" --security-group "$SECGROUP" \
      --wait "$name" >/dev/null
  fi
done

echo "== 6/6 floating IP sulla prima VM =="
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

echo
echo "Progetto demo pronto. Per vedere cosa dovrebbe trovare la scansione:"
echo "  openstack server list      --project $PROJECT"
echo "  openstack port list        --project $PROJECT"
echo "  openstack floating ip list --project $PROJECT"
