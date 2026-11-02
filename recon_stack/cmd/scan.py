# Il comando recon-stack-scan: esegue a mano una scansione di un progetto.
#
# Serve a provare gli Step 6 e 7 (docs/piano.md) prima che la scansione sia
# avviata dallo scheduler (step 10) o dalla API (step 8). Si lancia su DevStack
# come root o con i privilegi per oslo.privsep, indicando il progetto demo:
# registra una scansione, la esegue (perimetro, inventario, host discovery,
# service discovery) e stampa un riepilogo degli host, con i servizi trovati.
#
# Uso (sul nodo DevStack):
#   sudo recon-stack-scan --project recon-demo \
#       --config-file /etc/recon-stack/recon-stack.conf

import argparse
import logging
import sys

from recon_stack import conf
from recon_stack.db import api as db
from recon_stack.db import models
from recon_stack.scanner import cloud
from recon_stack.scanner import scan as scan_mod

LOG = logging.getLogger(__name__)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv

    parser = argparse.ArgumentParser(
        prog="recon-stack-scan",
        description="Esegue una scansione di un progetto.")
    parser.add_argument("--project", required=True,
                        help="Nome o id del progetto da scansionare.")
    args, rest = parser.parse_known_args(argv)
    conf.load(rest)

    conn = cloud.connect()
    project = conn.identity.find_project(args.project, ignore_missing=True)
    if project is None:
        LOG.error("progetto '%s' non trovato", args.project)
        return 1

    # Registriamo la scansione (trigger manuale) e la eseguiamo. Questo comando
    # lo lancia l'amministratore sul nodo, come "nova-manage": non passa dalla
    # API, quindi non applica il controllo del ruolo (quello vale per le
    # richieste HTTP, api/scans.py).
    scan = db.create_scan(project.id, models.TRIGGER_MANUAL,
                          status=models.SCAN_PENDING)
    scan = scan_mod.run_scan(conn, scan.id)

    print(f"Scansione {scan.id} del progetto {project.name}: {scan.status}")
    if scan.fault:
        print(f"  motivo: {scan.fault}")
        return 1
    # Servizi trovati, raggruppati per host, per stamparli sotto il rispettivo
    # indirizzo (gli assenti non ne hanno: non rispondono).
    services_by_host = {}
    for svc in db.get_services(scan.id):
        services_by_host.setdefault(svc.host_id, []).append(svc)

    # Gli host censiti che non sono VM (router, DHCP, metadati di OVN) non hanno
    # un nome: li etichettiamo con il ruolo della loro porta Neutron, letto
    # dall'inventario della scansione (device_owner).
    owner_by_ip = {p.ip_address: p.device_owner
                   for p in db.get_inventory(scan.id)["ports"]}

    for label, value in (("censiti", models.HOST_KNOWN),
                         ("sconosciuti", models.HOST_UNKNOWN),
                         ("assenti", models.HOST_ABSENT)):
        hosts = db.get_hosts(scan.id, classification=value)
        print(f"  {label}: {len(hosts)}")
        for h in hosts:
            name = (h.server_name or _owner_label(owner_by_ip.get(h.ip_address))
                    or h.classification)
            print(f"    - {h.ip_address} ({name})")
            for svc in sorted(services_by_host.get(h.id, []),
                              key=lambda s: s.port_number):
                # Es. "22/tcp ssh OpenSSH 8.9p1"; i pezzi mancanti si saltano.
                descr = " ".join(p for p in (svc.name, svc.product, svc.version) if p)
                # Lo stesso servizio può comparire due volte: dall'interno della
                # rete e dall'esterno sul floating IP. Lo diciamo.
                where = " (vista esterna)" if svc.view == models.VIEW_EXTERNAL else ""
                print(f"        {svc.port_number}/{svc.protocol} {descr}".rstrip() + where)
    return 0


# Nomi leggibili per i ruoli più comuni delle porte Neutron (device_owner).
_OWNER_LABELS = {
    "network:router_interface": "router",
    "network:router_interface_distributed": "router",
    "network:dhcp": "DHCP",
    "network:distributed": "metadati OVN",
}


def _owner_label(device_owner):
    """Etichetta di una porta Neutron che non è una VM, es. "router"."""
    if not device_owner or device_owner.startswith("compute:"):
        return None
    return _OWNER_LABELS.get(device_owner, device_owner)


if __name__ == "__main__":
    sys.exit(main())
