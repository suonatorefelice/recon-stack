# Ambiente in cui alembic esegue le migrazioni.
#
# Alembic esegue questo file ogni volta che gli si chiede di applicare
# migrazioni (vedi recon_stack/db/migration.py). Il compito del file è dire ad
# alembic a quale database collegarsi e qual è lo schema atteso.

from alembic import context

from recon_stack.db import api
from recon_stack.db import models

# Lo schema descritto dalle classi in models.py: serve ad alembic per
# confrontarlo con il database (lo usa il test che controlla l'allineamento).
target_metadata = models.Base.metadata


def run_migrations():
    # Usiamo lo stesso motore del servizio, così valgono le stesse
    # impostazioni (per SQLite: WAL, busy_timeout, chiavi esterne).
    with api.get_engine().connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite sa fare poche modifiche alle tabelle esistenti (ad
            # esempio non sa togliere una colonna). In modalità "batch"
            # alembic aggira il limite: crea una tabella nuova con la forma
            # giusta, ci copia i dati e sostituisce la vecchia.
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations()
