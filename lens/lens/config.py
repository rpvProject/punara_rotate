"""Env-driven settings. Storage swaps to Postgres/ClickHouse at DSN level (ADR-001)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_LENS_DIR = Path(__file__).resolve().parents[1]  # .../lens (repo subdir, not the package)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LENS_", env_file=".env", extra="ignore")

    db_url: str = f"sqlite:///{(_LENS_DIR / 'lens.db').as_posix()}"
    olap_path: str = (_LENS_DIR / "lens_olap.duckdb").as_posix()
    api_host: str = "127.0.0.1"  # loopback only, never 0.0.0.0
    api_port: int = 8010


settings = Settings()
