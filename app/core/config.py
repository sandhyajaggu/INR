from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "INR MLA CRM"
    environment: str = "development"
    debug: bool = True

    # Security
    secret_key: str
    captcha_secret_key: str
    aadhaar_encryption_key: str

    # JWT
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    captcha_token_expire_minutes: int = 5

    # Database
    database_url: str

    # CORS — comma-separated origins
    cors_origins: str = "http://localhost:3000"

    # File storage
    storage_backend: str = "local"
    upload_dir: str = "uploads"
    upload_base_url: str = "/uploads"
    max_upload_size_mb: int = 25

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
