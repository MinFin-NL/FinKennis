"""Opslag van geüploade bestanden op schijf. Eén map per kennisbank."""

import hashlib
import uuid
from contextlib import suppress
from pathlib import Path

from fastapi import HTTPException, UploadFile

CHUNK_BYTES = 1024 * 1024


async def bewaar_upload(upload: UploadFile, map_: Path, max_bytes: int) -> tuple[Path, str, int]:
    """Schrijft de upload in stukken weg en berekent ondertussen de sha256.

    Het bestand houdt zijn extensie, want docling herkent het formaat daaraan.
    """
    map_.mkdir(parents=True, exist_ok=True)
    pad = map_ / f"{uuid.uuid4()}{Path(upload.filename or '').suffix.lower()}"
    sha = hashlib.sha256()
    grootte = 0
    try:
        with pad.open("wb") as f:
            while blok := await upload.read(CHUNK_BYTES):
                grootte += len(blok)
                if grootte > max_bytes:
                    raise HTTPException(
                        413, f"{upload.filename} is groter dan {max_bytes // (1024 * 1024)} MB."
                    )
                sha.update(blok)
                f.write(blok)
    except BaseException:
        pad.unlink(missing_ok=True)
        raise
    return pad, sha.hexdigest(), grootte


def verwijder_bestanden(paden: list[str]) -> None:
    for p in paden:
        with suppress(OSError):
            Path(p).unlink(missing_ok=True)
