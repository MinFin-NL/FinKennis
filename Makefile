BACKEND_PORT ?= 8400

.PHONY: install db migrate backend frontend dev lokaal test lint auth

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

# Alles in één keer, zonder inloggen: database, migraties, backend en frontend. Je bent de
# lokale dev-gebruiker. Omgevingsvariabelen gaan voor .env, dus dit werkt ook als daar
# AUTH_MODE=oidc staat. Gebruikersbeheer werkt zo niet; dat vraagt Keycloak (make auth).
lokaal:
	docker compose up -d --wait db
	$(MAKE) migrate
	AUTH_MODE=none VITE_AUTH_MODE=none $(MAKE) -j2 backend frontend

test:
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint
