"""Typed configuration read from the environment and `.env`."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


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

    # Optional. A Binance key with reading permission only, for the Portfolio screen.
    binance_api_key: SecretStr | None = None
    binance_api_secret: SecretStr | None = None

    # Optional. An email address the US regulator's site (SEC EDGAR) asks every program
    # to give as a contact before it serves company accounts. Sent to that site only.
    sec_contact: str | None = None

    postgres_user: str | None = None
    postgres_password: SecretStr | None = None
    postgres_db: str | None = None
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432

    # The API listens on this machine only by default. Containers set API_HOST=0.0.0.0.
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    log_level: str = "INFO"

    def database_url(self, database: str | None = None) -> URL:
        """SQLAlchemy URL for the configured database. Its repr hides the password."""
        if self.postgres_user is None or self.postgres_password is None or self.postgres_db is None:
            raise RuntimeError(
                "Database is not configured: set POSTGRES_USER, POSTGRES_PASSWORD and"
                " POSTGRES_DB in .env"
            )
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=database or self.postgres_db,
        )


def load_settings() -> Settings:
    return Settings()
