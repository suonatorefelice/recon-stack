# Il comando recon-stack-dbsync: crea o aggiorna le tabelle del database.
#
# Applica le migrazioni alembic che mancano (recon_stack/db/migration.py). Si
# può lanciare quante volte si vuole: se il database è già aggiornato non fa
# niente. Il plugin DevStack lo esegue nella fase post-config, prima di avviare
# i processi. Il nome segue la convenzione dei componenti OpenStack
# (nova-manage db sync, glance-manage db_sync, ...).
#
# Uso:
#   recon-stack-dbsync --config-file /etc/recon-stack/recon-stack.conf

import logging
import sys

from recon_stack import conf
from recon_stack.db import migration

LOG = logging.getLogger(__name__)


def main(argv=None):
    conf.load(sys.argv[1:] if argv is None else argv)
    before = migration.current_revision()
    migration.upgrade()
    after = migration.current_revision()
    if before == after:
        LOG.info("database già aggiornato (revisione %s)", after)
    else:
        LOG.info("database aggiornato dalla revisione %s alla %s", before, after)


if __name__ == "__main__":
    main()
