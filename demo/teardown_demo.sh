#!/usr/bin/env bash
#
# Cancella il progetto demo creato da setup_demo.sh, con tutte le sue risorse:
# VM, floating IP, router, rete, security group, utente e progetto.
#
# Serve a ripartire da zero, ad esempio prima di una dimostrazione o dopo aver
# cambiato setup_demo.sh. Tocca SOLO le risorse del progetto recon-demo.
# Non cancella le scansioni nel database di Recon-Stack: restano come storico.
#
# USO (sul nodo DevStack, dopo aver caricato le credenziali admin):
#   source /opt/stack/devstack/openrc admin admin
#   bash demo/teardown_demo.sh
#
# Ogni passo tollera le risorse già sparite, quindi lo script si può ripetere.

set -uo pipefail

PROJECT=recon-demo
USER_NAME=recon-demo-user
NET=recon-demo-net
SUBNET=recon-demo-subnet
ROUTER=recon-demo-router
SECGROUP=recon-demo-sg

if [[ -z "${OS_AUTH_URL:-}" ]]; then
  echo "ERRORE: carica prima le credenziali admin, es.:" >&2
  echo "  source /opt/stack/devstack/openrc admin admin" >&2
  exit 1
fi

PROJECT_ID=$(openstack project show "$PROJECT" -f value -c id 2>/dev/null)
if [[ -z "$PROJECT_ID" ]]; then
  echo "Il progetto $PROJECT non esiste: niente da cancellare."
  exit 0
fi

# L'ordine conta: Neutron non cancella una rete con porte attaccate né un router
# con interfacce, quindi si va dall'esterno verso l'interno.

echo "== 1/6 VM =="
for id in $(openstack server list --project "$PROJECT_ID" -f value -c ID); do
  openstack server delete --wait "$id" && echo "   cancellata VM $id"
done

echo "== 2/6 floating IP =="
for id in $(openstack floating ip list --project "$PROJECT_ID" -f value -c ID); do
  openstack floating ip delete "$id" && echo "   cancellato floating IP $id"
done

echo "== 3/6 router =="
ROUTER_ID=$(openstack router list --project "$PROJECT_ID" -f value -c ID -c Name \
            | awk -v n="$ROUTER" '$2 == n {print $1}')
if [[ -n "$ROUTER_ID" ]]; then
  openstack router remove subnet "$ROUTER_ID" "$SUBNET" 2>/dev/null
  openstack router unset --external-gateway "$ROUTER_ID" 2>/dev/null
  openstack router delete "$ROUTER_ID" && echo "   cancellato router $ROUTER"
fi

echo "== 4/6 rete e subnet =="
NET_ID=$(openstack network list --project "$PROJECT_ID" -f value -c ID -c Name \
         | awk -v n="$NET" '$2 == n {print $1}')
if [[ -n "$NET_ID" ]]; then
  # Cancellando la rete Neutron toglie anche la subnet e le sue porte di servizio.
  openstack network delete "$NET_ID" && echo "   cancellata rete $NET"
fi

echo "== 5/6 security group =="
for id in $(openstack security group list --project "$PROJECT_ID" -f value -c ID -c Name \
            | awk -v n="$SECGROUP" '$2 == n {print $1}'); do
  openstack security group delete "$id" && echo "   cancellato security group $SECGROUP"
done

echo "== 6/6 utente e progetto =="
openstack user delete "$USER_NAME" 2>/dev/null && echo "   cancellato utente $USER_NAME"
# Il security group "default" del progetto lo crea Neutron da sé: va tolto prima
# del progetto, altrimenti resta orfano.
for id in $(openstack security group list --project "$PROJECT_ID" -f value -c ID); do
  openstack security group delete "$id" 2>/dev/null
done
openstack project delete "$PROJECT_ID" && echo "   cancellato progetto $PROJECT"

echo
echo "Progetto demo cancellato. Per ricrearlo: bash demo/setup_demo.sh"
