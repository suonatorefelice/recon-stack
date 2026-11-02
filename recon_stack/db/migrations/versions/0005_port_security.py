"""Quinta migrazione: stato della port security delle porte dell'inventario.

Aggiunge a inventory_ports la colonna port_security_enabled. Una porta con la
port security disattivata non è protetta da nessun security group: senza questa
informazione il motore di esposizione la scambiava per una porta senza regole e
segnalava i suoi servizi come "latenti", mentre sono raggiungibili da tutta la
rete (trovato nel test su DevStack). Il significato della colonna è spiegato in
InventoryPort, in recon_stack/db/models.py.

Nullable: le scansioni salvate prima di questa migrazione non hanno il dato.
Come le precedenti, questa migrazione va solo "in avanti" (nessun downgrade).
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "inventory_ports",
        sa.Column("port_security_enabled", sa.Boolean(), nullable=True))
