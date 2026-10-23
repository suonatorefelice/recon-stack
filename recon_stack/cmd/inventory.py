# Il comando recon-stack-inventory: raccoglie e salva l'inventario di un
# progetto, a mano.
#
# Serve a provare lo Step 4 (docs/piano.md) prima che esista la scansione
# completa: si lancia su DevStack indicando il progetto demo, legge VM, porte e
# floating IP da Nova e Neutron, li salva in una nuova scansione e stampa un
# riepilogo. Il riepilogo si confronta con:
#   openstack server list      --project recon-demo
#   openstack port list        --project recon-demo
#   openstack floating ip list --project recon-demo
#
# Più avanti (Step 5-6) la raccolta diventerà il primo passo di una scansione
# vera avviata dallo scanner; questo comando resta comodo per il debug.
#
# Uso:
#   recon-stack-inventory --project recon-demo
#   recon-stack-inventory --project <id> --config-file /etc/recon-stack/recon-stack.conf

import argparse
import logging
import sys

from recon_stack import conf
from recon_stack.db import api
from recon_stack.db import models
from recon_stack.scanner import cloud
from recon_stack.scanner import inventory

LOG = logging.getLogger(__name__)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv

    # --project è nostro; gli altri argomenti (es. --config-file) li gestisce
    # oslo.config dentro conf.load, quindi li lasciamo passare con
    # parse_known_args e glieli giriamo.
    parser = argparse.ArgumentParser(
        prog="recon-stack-inventory",
        description="Raccoglie l'inventario di un progetto e lo salva.")
    parser.add_argument("--project", required=True,
                        help="Nome o id del progetto da inventariare.")
    args, rest = parser.parse_known_args(argv)
    conf.load(rest)

    conn = cloud.connect()

    # Accettiamo sia il nome sia l'id: find_project risolve il nome nell'id che
    # usiamo come chiave nel database.
    project = conn.identity.find_project(args.project, ignore_missing=True)
    if project is None:
        LOG.error("progetto '%s' non trovato", args.project)
        return 1
    project_id = project.id

    scan = api.create_scan(project_id, models.TRIGGER_MANUAL,
                           status=models.SCAN_RUNNING)
    servers, ports, floating_ips = inventory.collect_and_save(
        conn, project_id, scan.id)

    print(f"Inventario del progetto {project.name} ({project_id}),"
          f" scansione {scan.id}:")
    print(f"  VM:           {len(servers)}")
    for s in servers:
        print(f"    - {s.name} [{s.status}] {s.server_id}")
    print(f"  IP di porta:  {len(ports)}")
    for p in ports:
        print(f"    - {p.ip_address} ({p.device_owner or 'n/d'}) porta {p.port_id}")
    print(f"  floating IP:  {len(floating_ips)}")
    for f in floating_ips:
        print(f"    - {f.floating_ip_address} -> {f.fixed_ip_address or 'n/d'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
