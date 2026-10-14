from functools import lru_cache

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
