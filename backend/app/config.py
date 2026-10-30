from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://shelfiq:shelfiq@localhost:5432/shelfiq"
    # Connection used by the AI analyst. Point it at a read-only role in production.
    analyst_database_url: str | None = None
    redis_url: str | None = None

    jwt_secret: str = "dev-only-secret-change-me-in-production"
    jwt_ttl_hours: int = 24
    cors_origins: str = "http://localhost:3000"
    # e.g. https://shelfiq-.*\.vercel\.app to allow Vercel preview deployments
    cors_origin_regex: str | None = None

    # LLM providers are tried in this order: Groq, then Gemini. Both expose
    # OpenAI-compatible endpoints, so one client handles both.
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    llm_timeout_s: float = 30.0

    ai_daily_limit: int = 20
    ai_minute_limit: int = 5
    sql_row_limit: int = 200
    sql_timeout_ms: int = 5000

    # Set false on the public demo, so visitors cannot change the figures others see.
    data_writes_enabled: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_test(self) -> bool:
        return self.environment == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()
