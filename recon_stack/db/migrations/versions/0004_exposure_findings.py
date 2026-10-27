"""Quarta migrazione: segnalazioni di esposizione (step 11).

Crea la tabella exposure_findings, dove la scansione salva le segnalazioni
prodotte dal confronto fra i servizi trovati e i security group (regola inutile,
servizio latente, esposizione eccessiva, host non censito, floating IP inutile).
Le colonne corrispondono alla classe ExposureFinding in recon_stack/db/models.py.

Come le precedenti, questa migrazione va solo "in avanti" (nessun downgrade).
"""

from alembic import op
import sqlalchemy as sa

# Numero di questa migrazione e di quella che la precede (la 0003).
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "exposure_findings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scan_id", sa.String(36), sa.ForeignKey("scans.id"), nullable=False),
        sa.Column("finding_type", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("port_number", sa.Integer(), nullable=True),
        sa.Column("protocol", sa.String(8), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_exposure_findings_scan_id", "exposure_findings", ["scan_id"])
    op.create_index(
        "ix_exposure_findings_ip_address", "exposure_findings", ["ip_address"])
