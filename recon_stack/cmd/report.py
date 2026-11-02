# Il comando recon-stack-report: genera il report di una scansione (step 12).
#
# Trasforma i risultati di una scansione già fatta (host, servizi, segnalazioni)
# in un report HTML con la mappa della topologia, più una versione con redaction
# da condividere. Non esegue scansioni: legge dal database. OpenStack serve solo
# per tradurre il nome del progetto (--project recon-demo) nel suo id; se non è
# raggiungibile, il valore di --project si usa direttamente come id, così il
# report si genera anche dove c'è solo il database.
#
# Uso (sul nodo DevStack, o ovunque ci sia il database della scansione):
#   recon-stack-report --scan <id> --output /tmp/report
#   recon-stack-report --project recon-demo --redacted --pdf
#
# Senza --scan usa l'ultima scansione completata (del progetto, se indicato).

import argparse
import logging
import sys

from recon_stack import conf
from recon_stack.db import api as db
from recon_stack.db import models
from recon_stack.report import render
from recon_stack.scanner import cloud

LOG = logging.getLogger(__name__)


def _project_id(name_or_id):
    """Id del progetto da --project, che può essere un nome o un id.

    Nel database le scansioni sono legate all'id del progetto. Nella prima
    versione il nome veniva cercato come se fosse un id e il comando non
    trovava mai niente (trovato nel test su DevStack): ora lo risolviamo con
    Keystone, come fanno recon-stack-scan e i comandi "openstack recon".
    """
    try:
        project = cloud.connect().identity.find_project(
            name_or_id, ignore_missing=True)
    except Exception:
        LOG.warning("OpenStack non raggiungibile: uso '%s' come id del progetto",
                    name_or_id)
        return name_or_id
    if project is None:
        LOG.warning("progetto '%s' non trovato in Keystone: lo uso come id",
                    name_or_id)
        return name_or_id
    return project.id


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv

    parser = argparse.ArgumentParser(
        prog="recon-stack-report",
        description="Genera il report HTML di una scansione.")
    parser.add_argument("--scan", help="Id della scansione da riportare.")
    parser.add_argument("--project",
                        help="Se non si dà --scan, prende l'ultima scansione "
                             "completata di questo progetto (nome o id).")
    parser.add_argument("--output", default=".",
                        help="Cartella dove scrivere i file (default: corrente).")
    parser.add_argument("--redacted", action="store_true",
                        help="Produce la versione condivisibile, con pseudonimi.")
    parser.add_argument("--pdf", action="store_true",
                        help="Prova a generare anche il PDF (serve weasyprint).")
    args, rest = parser.parse_known_args(argv)
    conf.load(rest)

    scan_id = args.scan
    if not scan_id:
        project_id = _project_id(args.project) if args.project else None
        scan = db.get_latest_scan(project_id=project_id,
                                  status=models.SCAN_DONE)
        if scan is None:
            LOG.error("nessuna scansione completata da riportare")
            return 1
        scan_id = scan.id

    written = render.generate(scan_id, output_dir=args.output,
                              redacted=args.redacted, pdf=args.pdf)
    if written is None:
        LOG.error("scansione '%s' non trovata", scan_id)
        return 1

    print(f"Report della scansione {scan_id}:")
    for kind, path in written.items():
        print(f"  {kind}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
