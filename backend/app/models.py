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
    Uuid,
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
    # Hoe vaak de worker het document heeft opgepakt. Loopt op als de backend tijdens het
    # verwerken stopt (bijv. geheugen op), zodat één document niet eindeloos blijft crashen.
    pogingen: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Inzichten worden na het verwerken gemaakt, in een eigen stap met een eigen status:
    # het document is al doorzoekbaar terwijl de inzichten nog lopen.
    inzichten_status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status", create_type=False),
        default=DocumentStatus.wachtrij,
        server_default=DocumentStatus.wachtrij.value,
        index=True,
    )
    inzichten_foutmelding: Mapped[str | None] = mapped_column(Text)
    inzichten_pogingen: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    aantal_inzichten: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Voortgang van het lezen, en de bevindingen per gelezen sectie, zodat het na een herstart
    # verdergaat in plaats van opnieuw begint. Leeg zodra de inzichten klaar zijn.
    inzichten_secties_klaar: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    inzichten_secties_totaal: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    inzichten_tussenstand: Mapped[dict | None] = mapped_column(JSONB)
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


class Inzicht(Base):
    """Een bevinding uit een document, vooraf gemaakt door het hele document te lezen.

    chunk_ids verwijst naar de fragmenten waar het inzicht op steunt; die zijn de bronnen.
    """

    __tablename__ = "inzicht"
    __table_args__ = (
        Index(
            "ix_inzicht_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), index=True
    )
    kennisbank_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("kennisbank.id", ondelete="CASCADE"), index=True
    )
    volgnummer: Mapped[int] = mapped_column(Integer)  # 0 is het belangrijkste
    thema: Mapped[str] = mapped_column(String(200))
    soort: Mapped[str] = mapped_column(String(30))
    belang: Mapped[int] = mapped_column(Integer)  # 1 (laag) t/m 3 (hoog)
    tekst: Mapped[str] = mapped_column(Text)
    chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(Uuid))
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM))


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
    modus: Mapped[str] = mapped_column(String(20), default="vraag", server_default="vraag")
    inhoud: Mapped[str] = mapped_column(Text)
    bronnen: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )

    gesprek: Mapped[Gesprek] = relationship(back_populates="berichten")
