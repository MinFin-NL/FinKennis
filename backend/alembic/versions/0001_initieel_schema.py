"""initieel schema

Revision ID: 31c427e06ea8
Revises:
Create Date: 2026-10-28 14:04:31.432201
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "31c427e06ea8"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "kennisbank",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_sub", sa.String(length=255), nullable=False),
        sa.Column("naam", sa.String(length=200), nullable=False),
        sa.Column("omschrijving", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_kennisbank_owner_sub"), "kennisbank", ["owner_sub"], unique=False)
    op.create_table(
        "document",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kennisbank_id", sa.Uuid(), nullable=False),
        sa.Column("bestandsnaam", sa.String(length=500), nullable=False),
        sa.Column("mime", sa.String(length=200), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("grootte", sa.Integer(), nullable=False),
        sa.Column("pad", sa.String(length=1000), nullable=False),
        sa.Column(
            "status",
            sa.Enum("wachtrij", "verwerken", "gereed", "fout", name="document_status"),
            nullable=False,
        ),
        sa.Column("foutmelding", sa.Text(), nullable=True),
        sa.Column("aantal_chunks", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["kennisbank_id"], ["kennisbank.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kennisbank_id", "sha256", name="uq_document_sha256"),
    )
    op.create_index(op.f("ix_document_kennisbank_id"), "document", ["kennisbank_id"], unique=False)
    op.create_index(op.f("ix_document_status"), "document", ["status"], unique=False)
    op.create_table(
        "gesprek",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kennisbank_id", sa.Uuid(), nullable=False),
        sa.Column("owner_sub", sa.String(length=255), nullable=False),
        sa.Column("titel", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["kennisbank_id"], ["kennisbank.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_gesprek_kennisbank_id"), "gesprek", ["kennisbank_id"], unique=False)
    op.create_index(op.f("ix_gesprek_owner_sub"), "gesprek", ["owner_sub"], unique=False)
    op.create_table(
        "bericht",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("gesprek_id", sa.Uuid(), nullable=False),
        sa.Column("rol", sa.String(length=20), nullable=False),
        sa.Column("inhoud", sa.Text(), nullable=False),
        sa.Column("bronnen", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["gesprek_id"], ["gesprek.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bericht_gesprek_id"), "bericht", ["gesprek_id"], unique=False)
    op.create_table(
        "chunk",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("kennisbank_id", sa.Uuid(), nullable=False),
        sa.Column("volgnummer", sa.Integer(), nullable=False),
        sa.Column("tekst", sa.Text(), nullable=False),
        sa.Column("kopjes", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("pagina", sa.Integer(), nullable=True),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=768), nullable=False),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('dutch', tekst)", persisted=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["kennisbank_id"], ["kennisbank.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chunk_document_id"), "chunk", ["document_id"], unique=False)
    op.create_index(
        "ix_chunk_embedding_hnsw",
        "chunk",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(op.f("ix_chunk_kennisbank_id"), "chunk", ["kennisbank_id"], unique=False)
    op.create_index("ix_chunk_tsv", "chunk", ["tsv"], unique=False, postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_chunk_tsv", table_name="chunk", postgresql_using="gin")
    op.drop_index(op.f("ix_chunk_kennisbank_id"), table_name="chunk")
    op.drop_index(
        "ix_chunk_embedding_hnsw",
        table_name="chunk",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_index(op.f("ix_chunk_document_id"), table_name="chunk")
    op.drop_table("chunk")
    op.drop_index(op.f("ix_bericht_gesprek_id"), table_name="bericht")
    op.drop_table("bericht")
    op.drop_index(op.f("ix_gesprek_owner_sub"), table_name="gesprek")
    op.drop_index(op.f("ix_gesprek_kennisbank_id"), table_name="gesprek")
    op.drop_table("gesprek")
    op.drop_index(op.f("ix_document_status"), table_name="document")
    op.drop_index(op.f("ix_document_kennisbank_id"), table_name="document")
    op.drop_table("document")
    op.drop_index(op.f("ix_kennisbank_owner_sub"), table_name="kennisbank")
    op.drop_table("kennisbank")
    op.execute("DROP TYPE IF EXISTS document_status")
