"""inzichten

Revision ID: 8c3f0a6d2e71
Revises: 5b1e7d2c9a40
Create Date: 2026-11-05 10:00:00.000000
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "8c3f0a6d2e71"
down_revision: str | None = "5b1e7d2c9a40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUS = postgresql.ENUM(
    "wachtrij", "verwerken", "gereed", "fout", name="document_status", create_type=False
)


def upgrade() -> None:
    # server_default 'wachtrij': bestaande documenten krijgen hun inzichten alsnog.
    op.add_column(
        "document",
        sa.Column("inzichten_status", STATUS, server_default="wachtrij", nullable=False),
    )
    op.create_index("ix_document_inzichten_status", "document", ["inzichten_status"])
    op.add_column("document", sa.Column("inzichten_foutmelding", sa.Text(), nullable=True))
    op.add_column(
        "document",
        sa.Column("inzichten_pogingen", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "document", sa.Column("aantal_inzichten", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "bericht", sa.Column("modus", sa.String(20), server_default="vraag", nullable=False)
    )

    op.create_table(
        "inzicht",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("kennisbank_id", sa.Uuid(), nullable=False),
        sa.Column("volgnummer", sa.Integer(), nullable=False),
        sa.Column("thema", sa.String(200), nullable=False),
        sa.Column("soort", sa.String(30), nullable=False),
        sa.Column("belang", sa.Integer(), nullable=False),
        sa.Column("tekst", sa.Text(), nullable=False),
        sa.Column("chunk_ids", postgresql.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=768), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["kennisbank_id"], ["kennisbank.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inzicht_document_id", "inzicht", ["document_id"])
    op.create_index("ix_inzicht_kennisbank_id", "inzicht", ["kennisbank_id"])
    op.create_index(
        "ix_inzicht_embedding_hnsw",
        "inzicht",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_table("inzicht")
    op.drop_column("bericht", "modus")
    op.drop_column("document", "aantal_inzichten")
    op.drop_column("document", "inzichten_pogingen")
    op.drop_column("document", "inzichten_foutmelding")
    op.drop_index("ix_document_inzichten_status", table_name="document")
    op.drop_column("document", "inzichten_status")
