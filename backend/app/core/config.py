from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── App ──
    APP_NAME: str = "Agentic Payments Orchestrator"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # ── Database (Neon) ──
    DATABASE_URL: str = ""          # async: postgresql+asyncpg://...
    SYNC_DATABASE_URL: str = ""     # sync:  postgresql+psycopg2://...

    # ── Redis ──
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── JWT ──
    SECRET_KEY: str = "change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Stripe ──
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # ── Gemini ──
    GEMINI_API_KEY: str = ""

    # ── Payment provider ──
    PAYMENT_PROVIDER: str = "mock"  # "stripe" | "mock"

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()
