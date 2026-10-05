import pytest
from pydantic import SecretStr

from radar.config import Settings

PASSWORD = "not-a-real-password"  # noqa: S105


def settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "postgres_user": "radar",
        "postgres_password": SecretStr(PASSWORD),
        "postgres_db": "radar",
        "postgres_port": 5433,
    }
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[arg-type]


def test_database_url_uses_psycopg_and_configured_port() -> None:
    url = settings().database_url()
    assert url.drivername == "postgresql+psycopg"
    assert (url.host, url.port, url.database) == ("127.0.0.1", 5433, "radar")
    assert settings().database_url("radar_test").database == "radar_test"


def test_password_is_hidden_in_reprs() -> None:
    config = settings()
    for text in (
        repr(config),
        str(config),
        repr(config.database_url()),
        str(config.database_url()),
    ):
        assert PASSWORD not in text


def test_missing_database_settings_raise_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="POSTGRES_USER"):
        settings(postgres_password=None).database_url()
