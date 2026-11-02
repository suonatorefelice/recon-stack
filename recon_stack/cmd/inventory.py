# Il comando recon-stack-inventory: legge e mostra l'inventario di un progetto,
# a mano, senza salvarlo.
#
# Serve a provare lo Step 4 (docs/piano.md): si lancia su DevStack indicando il
# progetto demo, legge VM, porte, floating IP e security group da Nova e
# Neutron e stampa un riepilogo. Il riepilogo si confronta con:
#   openstack server list      --project recon-demo
#   openstack port list        --project recon-demo
#   openstack floating ip list --project recon-demo
#
# Il comando è di sola lettura: non crea scansioni nel database. Nella prima
# versione salvava l'inventario in una scansione nuova lasciata in RUNNING per
# sempre (nessuno la chiudeva), che compariva in "openstack recon scan list"
# (trovato nel test su DevStack). L'inventario salvato lo produce la scansione
# vera (recon-stack-scan o POST /v1/scans), di cui è il primo passo.
#
# Uso:
#   recon-stack-inventory --project recon-demo
#   recon-stack-inventory --project <id> --config-file /etc/recon-stack/recon-stack.conf

import argparse
import logging
import sys

from recon_stack import conf
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
        description="Legge e mostra l'inventario di un progetto, senza salvarlo.")
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

    # scan_id=None: gli oggetti non sono legati a nessuna scansione e non
    # vengono salvati (collect legge soltanto, vedi scanner/inventory.py).
    servers, ports, floating_ips, security_groups, rules = inventory.collect(
        conn, project_id, None)

    print(f"Inventario del progetto {project.name} ({project_id}),"
          " sola lettura:")
    print(f"  VM:           {len(servers)}")
    for s in servers:
        print(f"    - {s.name} [{s.status}] {s.server_id}")
    print(f"  IP di porta:  {len(ports)}")
    for p in ports:
        print(f"    - {p.ip_address} ({p.device_owner or 'n/d'}) porta {p.port_id}")
    print(f"  floating IP:  {len(floating_ips)}")
    for f in floating_ips:
        print(f"    - {f.floating_ip_address} -> {f.fixed_ip_address or 'n/d'}")
    print(f"  security group: {len(security_groups)} ({len(rules)} regole)")
    for sg in security_groups:
        print(f"    - {sg.name} {sg.security_group_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
