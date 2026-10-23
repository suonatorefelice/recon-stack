"""Prima migrazione: crea le tabelle scans, hosts e services.

Le colonne corrispondono alle classi in recon_stack/db/models.py, dove è
spiegato il significato di ognuna.

Le migrazioni vanno solo "in avanti" (upgrade): non scriviamo il downgrade,
come fanno i componenti OpenStack, perché tornare indietro su un database con
dati veri si fa ripristinando una copia, non disfacendo lo schema.
"""

from alembic import op
import sqlalchemy as sa

# Numero di questa migrazione e di quella che la precede (nessuna: è la prima).
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "scans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(64), nullable=False),
        sa.Column("trigger", sa.String(16), nullable=False),
        sa.Column("requested_by_user", sa.String(64), nullable=True),
        sa.Column("requested_by_project", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("perimeter", sa.Text(), nullable=True),
        sa.Column("fault", sa.Text(), nullable=True),
    )
    op.create_index("ix_scans_project_id", "scans", ["project_id"])
    op.create_index("ix_scans_status", "scans", ["status"])

    op.create_table(
        "hosts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scan_id", sa.String(36), sa.ForeignKey("scans.id"), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("network_id", sa.String(36), nullable=True),
        sa.Column("subnet_id", sa.String(36), nullable=True),
        sa.Column("neutron_port_id", sa.String(36), nullable=True),
        sa.Column("server_id", sa.String(36), nullable=True),
        sa.Column("server_name", sa.String(255), nullable=True),
        sa.Column("classification", sa.String(16), nullable=False),
    )
    op.create_index("ix_hosts_scan_id", "hosts", ["scan_id"])
    op.create_index("ix_hosts_ip_address", "hosts", ["ip_address"])

    op.create_table(
        "services",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("host_id", sa.String(36), sa.ForeignKey("hosts.id"), nullable=False),
        sa.Column("port_number", sa.Integer(), nullable=False),
        sa.Column("protocol", sa.String(8), nullable=False),
        sa.Column("name", sa.String(64), nullable=True),
        sa.Column("product", sa.String(255), nullable=True),
        sa.Column("version", sa.String(255), nullable=True),
        sa.Column("view", sa.String(16), nullable=False),
    )
    op.create_index("ix_services_host_id", "services", ["host_id"])
    op.create_index("ix_services_name", "services", ["name"])
