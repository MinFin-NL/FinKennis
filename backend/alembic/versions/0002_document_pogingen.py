"""document pogingen

Revision ID: 5b1e7d2c9a40
Revises: 31c427e06ea8
Create Date: 2026-10-29 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5b1e7d2c9a40"
down_revision: str | None = "31c427e06ea8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document", sa.Column("pogingen", sa.Integer(), server_default="0", nullable=False)
    )


def downgrade() -> None:
    op.drop_column("document", "pogingen")
