from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str = "postgresql+asyncpg://finkennis:finkennis@localhost:5433/finkennis"

    ollama_url: str = "http://localhost:11434"
    chat_model: str = "qwen3:8b"
    embed_model: str = "nomic-embed-text"
    embed_dim: int = 768
    embed_batch_size: int = 32

    upload_dir: Path = Path("uploads")
    max_upload_mb: int = 50
    ingest_concurrency: int = 1
    ingest_worker_enabled: bool = True

    chunk_max_tokens: int = 512
    retrieval_candidates: int = 20
    retrieval_top_k: int = 6
    history_messages: int = 6

    cors_origins: list[str] = ["http://localhost:5190"]

    auth_mode: Literal["none", "oidc"] = "none"
    oidc_issuer: str = "http://localhost:8180/realms/finkennis"
    oidc_audience: str = "finkennis-api"
    # Service account voor gebruikersbeheer via de Keycloak Admin REST API.
    oidc_admin_client_id: str = "finkennis-admin"
    oidc_admin_client_secret: str = "dev-admin-secret-change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()
