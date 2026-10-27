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

    for label, value in (("censiti", models.HOST_KNOWN),
                         ("sconosciuti", models.HOST_UNKNOWN),
                         ("assenti", models.HOST_ABSENT)):
        hosts = db.get_hosts(scan.id, classification=value)
        print(f"  {label}: {len(hosts)}")
        for h in hosts:
            name = h.server_name or h.classification
            print(f"    - {h.ip_address} ({name})")
            for svc in sorted(services_by_host.get(h.id, []),
                              key=lambda s: s.port_number):
                # Es. "22/tcp ssh OpenSSH 8.9p1"; i pezzi mancanti si saltano.
                descr = " ".join(p for p in (svc.name, svc.product, svc.version) if p)
                print(f"        {svc.port_number}/{svc.protocol} {descr}".rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
