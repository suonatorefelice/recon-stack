"""Terza migrazione: inventario dei security group (step 11).

Aggiunge due tabelle per salvare la "fotografia" dei security group del progetto
all'inizio di una scansione (inventory_security_groups e inventory_sg_rules) e
una colonna a inventory_ports con l'elenco dei security group applicati a ogni
porta. Servono al confronto fra le regole e i servizi davvero in ascolto, da cui
nascono le segnalazioni di esposizione. Le colonne corrispondono alle classi in
recon_stack/db/models.py, dove è spiegato il significato di ognuna.

Come le precedenti, questa migrazione va solo "in avanti" (nessun downgrade).
"""

from alembic import op
import sqlalchemy as sa

# Numero di questa migrazione e di quella che la precede (la 0002).
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inventory_security_groups",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scan_id", sa.String(36), sa.ForeignKey("scans.id"), nullable=False),
        sa.Column("security_group_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_inventory_security_groups_scan_id",
        "inventory_security_groups", ["scan_id"])
    op.create_index(
        "ix_inventory_security_groups_security_group_id",
        "inventory_security_groups", ["security_group_id"])

    op.create_table(
        "inventory_sg_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scan_id", sa.String(36), sa.ForeignKey("scans.id"), nullable=False),
        sa.Column("rule_id", sa.String(36), nullable=False),
        sa.Column("security_group_id", sa.String(36), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("ethertype", sa.String(16), nullable=True),
        sa.Column("protocol", sa.String(16), nullable=True),
        sa.Column("port_range_min", sa.Integer(), nullable=True),
        sa.Column("port_range_max", sa.Integer(), nullable=True),
        sa.Column("remote_ip_prefix", sa.String(64), nullable=True),
        sa.Column("remote_group_id", sa.String(36), nullable=True),
    )
    op.create_index(
        "ix_inventory_sg_rules_scan_id", "inventory_sg_rules", ["scan_id"])
    op.create_index(
        "ix_inventory_sg_rules_rule_id", "inventory_sg_rules", ["rule_id"])
    op.create_index(
        "ix_inventory_sg_rules_security_group_id",
        "inventory_sg_rules", ["security_group_id"])

    # Nuova colonna su inventory_ports: i security group applicati alla porta,
    # come testo JSON (vedi InventoryPort in models.py).
    op.add_column(
        "inventory_ports",
        sa.Column("security_group_ids", sa.Text(), nullable=True))
