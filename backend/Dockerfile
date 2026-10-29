FROM python:3.13-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

# Afhankelijkheden eerst, voor de laagcache. Op Linux komt torch uit de CPU-index
# (zie [tool.uv.sources] in pyproject.toml).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# docling haalt zijn layout- en tabelmodellen anders bij de eerste PDF op, en dat
# opnieuw na elke herstart van de container. Bak ze in het image.
ENV DOCLING_ARTIFACTS_PATH=/opt/docling-models
RUN uv run --no-sync docling-tools models download layout tableformer -o "$DOCLING_ARTIFACTS_PATH"

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

EXPOSE 8000

# Migraties bij elke start: idempotent, en de database kan na een herstart van de
# Postgres-container leeg zijn (EmptyDir, zie azure-pipelines.yml).
CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && exec uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
