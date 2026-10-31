# Comando recon-stack-dbsync: crea lo schema del database (le tabelle definite in
# db/models.py, tramite db/api.py). Ripetibile: le tabelle già presenti
# restano. Il plugin DevStack lo esegue in post-config. Nome alla OpenStack
# (nova-manage db sync, ...). Uso:
#   recon-stack-dbsync --config-file /etc/recon-stack/recon-stack.conf

import logging
import sys

from recon_stack import conf
from recon_stack.db import api

LOG = logging.getLogger(__name__)


def main(argv=None):
    conf.load(sys.argv[1:] if argv is None else argv)
    api.create_all()
    LOG.info("schema del database pronto")


if __name__ == "__main__":
    main()
