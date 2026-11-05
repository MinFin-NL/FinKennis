"""inzichten voortgang

Revision ID: 2d9b4e7f1c58
Revises: 8c3f0a6d2e71
Create Date: 2026-11-05 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "2d9b4e7f1c58"
down_revision: str | None = "8c3f0a6d2e71"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document",
        sa.Column("inzichten_secties_klaar", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "document",
        sa.Column("inzichten_secties_totaal", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "document",
        sa.Column("inzichten_tussenstand", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document", "inzichten_tussenstand")
    op.drop_column("document", "inzichten_secties_totaal")
    op.drop_column("document", "inzichten_secties_klaar")
