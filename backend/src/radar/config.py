"""Typed configuration read from the environment and `.env`."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Secrets are `SecretStr`, so they are masked in reprs, logs, and tracebacks."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    alpaca_api_key_id: SecretStr | None = None
    alpaca_api_secret_key: SecretStr | None = None
    log_level: str = "INFO"


def load_settings() -> Settings:
    return Settings()
