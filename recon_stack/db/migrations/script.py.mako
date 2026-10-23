<%doc>
  Modello usato da "alembic revision" per creare il file di una nuova
  migrazione: alembic sostituisce i campi ${...} con i valori veri.
</%doc>
"""${message}

Revisione: ${up_revision}
Precedente: ${down_revision | comma,n}
"""

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade():
    ${upgrades if upgrades else "pass"}
