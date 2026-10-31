from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./sap_copilot.db"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    llm_max_tokens: int = 0  # 0 = provider default; e.g. 4096 if long answers get cut off

    frontend_origin: str = "http://localhost:5173"

    # Knowledge base (Phase 2). Paths are relative to where uvicorn is started (backend/).
    kb_dir: str = "../knowledge_base"
    embedding_backend: str = "fastembed"  # "fastembed" (real) or "hash" (offline tests only)
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    # Let the ABAP and Learning agents search the knowledge base before answering.
    rag_enabled: bool = True

    # Phase 4: syntax-check generated ABAP with abaplint and let the LLM fix what it finds.
    abaplint_enabled: bool = True
    abaplint_bin: str = ""  # empty = backend/tools/abaplint/node_modules/.bin/abaplint, then PATH
    abaplint_max_fixes: int = 2

    # Phase 3: SAP metadata catalog (YAML files). Empty catalog_dir = <kb_dir>/catalog.
    catalog_enabled: bool = True
    catalog_dir: str = ""

    # Interview coach: question bank folder. Empty = <kb_dir>/interview.
    interview_dir: str = ""
    # Error analyzer: knowledge folder. Empty = <kb_dir>/errors.
    errors_dir: str = ""

    # Hosted demo: usage limits for AI calls (0 = no limit). Counted per request, kept in memory.
    ai_limit_per_hour: int = 0  # per user
    ai_limit_per_day: int = 0  # for the whole server, per UTC day

    @field_validator("database_url")
    @classmethod
    def _use_psycopg2_driver(cls, v: str) -> str:
        """Neon, Render and Heroku hand out postgres:// or postgresql:// URLs; SQLAlchemy needs a driver name."""
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg2://" + v[len(prefix):]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


WEAK_JWT_SECRETS = {"", "change-me", "change-me-generate-a-long-random-string"}


def validate_jwt_secret(secret: str) -> None:
    """Refuse to run with a secret that is a placeholder or too short: tokens could be forged."""
    if secret in WEAK_JWT_SECRETS or len(secret) < 32:
        raise RuntimeError(
            "JWT_SECRET is missing, a placeholder or shorter than 32 characters. "
            'Generate one with: python -c "import secrets; print(secrets.token_hex(32))" '
            "and put it in backend/.env as JWT_SECRET=..."
        )
