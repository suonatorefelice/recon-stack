# Aggiornamento dello schema del database con alembic (ADR 0001).
#
# Una "migrazione" è un piccolo programma che porta lo schema da una versione
# alla successiva: la prima crea le tabelle, le successive aggiungono colonne
# o tabelle. Alembic tiene nel database stesso una tabella (alembic_version)
# con il numero dell'ultima migrazione applicata: "upgrade" esegue solo quelle
# che mancano. Così un database esistente si aggiorna senza perdere i dati, e
# un database nuovo si crea da zero eseguendole tutte in ordine.
#
# Di solito alembic si usa con un file alembic.ini e il comando "alembic". Qui
# lo configuriamo da Python, così l'indirizzo del database arriva dalla
# configurazione del servizio (recon-stack.conf) e non va ripetuto.

import pathlib

from alembic import command
from alembic import config as alembic_config
from alembic import migration as alembic_migration

from recon_stack.db import api

MIGRATIONS_DIR = pathlib.Path(__file__).parent / "migrations"


def _alembic_config():
    cfg = alembic_config.Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    return cfg


def upgrade(revision="head"):
    """Applica le migrazioni mancanti; "head" vuol dire "fino all'ultima"."""
    command.upgrade(_alembic_config(), revision)


def current_revision():
    """Numero dell'ultima migrazione applicata al database, None se nessuna."""
    with api.get_engine().connect() as connection:
        context = alembic_migration.MigrationContext.configure(connection)
        return context.get_current_revision()
