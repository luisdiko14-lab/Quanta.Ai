from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    app_name: str = "Quanta AI"
    app_env: str = "development"
    secret_key: str = "dev-only-change-me"
    frontend_base_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    database_url: str = "postgresql+asyncpg://quanta:quanta@localhost:5432/quanta"
    database_pool_size: int = 1
    database_max_overflow: int = 0
    database_pool_recycle_seconds: int = 300
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_requests: int = 20
    rate_limit_window_seconds: int = 60
    provider_timeout_seconds: float = 45.0
    provider_max_retries: int = 2
    ai_fallback_models: str = "gemini-free,groq-budget,deepseek-chat"

    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    gemini_model_free: str = ""
    gemini_model_premium: str = ""
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model_budget: str = ""
    groq_model_llama_70b: str = ""
    groq_model_qwen: str = ""
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model_chat: str = ""
    deepseek_model_reasoner: str = ""

    storage_root: str = "./storage"
    storage_backend: str = "local"
    r2_account_id: str = ""
    r2_bucket_name: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_endpoint_url: str = ""
    free_max_upload_size_mb: int = 10
    premium_max_upload_size_mb: int = 50
    provider_keys_encryption_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True

    @property
    def sqlalchemy_database_url(self) -> str:
        url = self.database_url.strip()
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def validate_runtime_secrets(self) -> None:
        unsafe_secrets = {
            "dev-only-change-me",
            "replace-this-with-a-long-random-secret-before-deploying",
        }
        if self.app_env.lower() == "production":
            if self.secret_key in unsafe_secrets or len(self.secret_key) < 32:
                raise RuntimeError(
                    "Set a unique SECRET_KEY of at least 32 characters before running in production."
                )
            if not self.sqlalchemy_database_url.startswith("postgresql+asyncpg://"):
                raise RuntimeError(
                    "DATABASE_URL must point to PostgreSQL and use the postgresql+asyncpg:// driver."
                )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
