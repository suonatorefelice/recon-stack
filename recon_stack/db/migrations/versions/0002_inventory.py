"""Seconda migrazione: crea le tabelle dell'inventario (step 4).

Le tabelle inventory_servers, inventory_ports e inventory_floating_ips
conservano la "fotografia" delle risorse lette da Nova e Neutron all'inizio di
una scansione. Le colonne corrispondono alle classi in recon_stack/db/models.py,
dove è spiegato il significato di ognuna.

Come la 0001, questa migrazione va solo "in avanti" (nessun downgrade).
"""

from alembic import op
import sqlalchemy as sa

# Numero di questa migrazione e di quella che la precede (la 0001).
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inventory_servers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scan_id", sa.String(36), sa.ForeignKey("scans.id"), nullable=False),
        sa.Column("server_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=True),
    )
    op.create_index("ix_inventory_servers_scan_id", "inventory_servers", ["scan_id"])
    op.create_index("ix_inventory_servers_server_id", "inventory_servers", ["server_id"])

    op.create_table(
        "inventory_ports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scan_id", sa.String(36), sa.ForeignKey("scans.id"), nullable=False),
        sa.Column("port_id", sa.String(36), nullable=False),
        sa.Column("network_id", sa.String(36), nullable=True),
        sa.Column("subnet_id", sa.String(36), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("mac_address", sa.String(32), nullable=True),
        sa.Column("device_owner", sa.String(64), nullable=True),
        sa.Column("device_id", sa.String(255), nullable=True),
    )
    op.create_index("ix_inventory_ports_scan_id", "inventory_ports", ["scan_id"])
    op.create_index("ix_inventory_ports_port_id", "inventory_ports", ["port_id"])
    op.create_index("ix_inventory_ports_ip_address", "inventory_ports", ["ip_address"])

    op.create_table(
        "inventory_floating_ips",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scan_id", sa.String(36), sa.ForeignKey("scans.id"), nullable=False),
        sa.Column("floating_ip_id", sa.String(36), nullable=False),
        sa.Column("floating_ip_address", sa.String(45), nullable=False),
        sa.Column("fixed_ip_address", sa.String(45), nullable=True),
        sa.Column("port_id", sa.String(36), nullable=True),
    )
    op.create_index(
        "ix_inventory_floating_ips_scan_id", "inventory_floating_ips", ["scan_id"])
    op.create_index(
        "ix_inventory_floating_ips_floating_ip_id",
        "inventory_floating_ips", ["floating_ip_id"])
    op.create_index(
        "ix_inventory_floating_ips_floating_ip_address",
        "inventory_floating_ips", ["floating_ip_address"])
