"""Sesta migrazione: fase corrente della scansione.

Aggiunge a scans la colonna phase. Lo scanner la aggiorna a ogni passo di una
scansione in corso (perimetro, inventario, scoperta, salvataggio, vista esterna,
esposizione) e la azzera a fine: serve solo a mostrare l'avanzamento nella
dashboard ("Scoperta host e servizi (3 di 6)"). Il significato della colonna è
spiegato in Scan, in recon_stack/db/models.py.

Nullable: le scansioni salvate prima di questa migrazione non hanno il dato.
Come le precedenti, questa migrazione va solo "in avanti" (nessun downgrade).
"""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "scans",
        sa.Column("phase", sa.String(32), nullable=True))
