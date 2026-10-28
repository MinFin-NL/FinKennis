import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import get_settings

EMBED_DIM = get_settings().embed_dim


class Base(DeclarativeBase):
    pass


class DocumentStatus(enum.StrEnum):
    wachtrij = "wachtrij"
    verwerken = "verwerken"
    gereed = "gereed"
    fout = "fout"


class Kennisbank(Base):
    __tablename__ = "kennisbank"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_sub: Mapped[str] = mapped_column(String(255), index=True)
    naam: Mapped[str] = mapped_column(String(200))
    omschrijving: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    documenten: Mapped[list["Document"]] = relationship(
        back_populates="kennisbank", cascade="all, delete-orphan", passive_deletes=True
    )


class Document(Base):
    __tablename__ = "document"
    __table_args__ = (UniqueConstraint("kennisbank_id", "sha256", name="uq_document_sha256"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kennisbank_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("kennisbank.id", ondelete="CASCADE"), index=True
    )
    bestandsnaam: Mapped[str] = mapped_column(String(500))
    mime: Mapped[str] = mapped_column(String(200), default="")
    sha256: Mapped[str] = mapped_column(String(64))
    grootte: Mapped[int] = mapped_column(Integer)
    pad: Mapped[str] = mapped_column(String(1000))
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status"), default=DocumentStatus.wachtrij, index=True
    )
    foutmelding: Mapped[str | None] = mapped_column(Text)
    aantal_chunks: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    kennisbank: Mapped[Kennisbank] = relationship(back_populates="documenten")


class Chunk(Base):
    __tablename__ = "chunk"
    __table_args__ = (
        Index(
            "ix_chunk_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunk_tsv", "tsv", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), index=True
    )
    kennisbank_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("kennisbank.id", ondelete="CASCADE"), index=True
    )
    volgnummer: Mapped[int] = mapped_column(Integer)
    tekst: Mapped[str] = mapped_column(Text)
    kopjes: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    pagina: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM))
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('dutch', tekst)", persisted=True)
    )


class Gesprek(Base):
    __tablename__ = "gesprek"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kennisbank_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("kennisbank.id", ondelete="CASCADE"), index=True
    )
    owner_sub: Mapped[str] = mapped_column(String(255), index=True)
    titel: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    berichten: Mapped[list["Bericht"]] = relationship(
        back_populates="gesprek",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Bericht.created_at",
    )


class Bericht(Base):
    __tablename__ = "bericht"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    gesprek_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("gesprek.id", ondelete="CASCADE"), index=True
    )
    rol: Mapped[str] = mapped_column(String(20))
    inhoud: Mapped[str] = mapped_column(Text)
    bronnen: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )

    gesprek: Mapped[Gesprek] = relationship(back_populates="berichten")
