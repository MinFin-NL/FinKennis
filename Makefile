BACKEND_PORT ?= 8400

.PHONY: install db migrate backend frontend dev test lint auth

install:
	cd backend && uv sync
	cd frontend && npm install

db:
	docker compose up -d db

auth:
	docker compose --profile auth up -d

migrate:
	cd backend && uv run alembic upgrade head

backend:
	cd backend && uv run uvicorn app.main:app --reload --port $(BACKEND_PORT)

frontend:
	cd frontend && BACKEND_PORT=$(BACKEND_PORT) npm run dev

dev:
	$(MAKE) -j2 backend frontend

test:
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint
