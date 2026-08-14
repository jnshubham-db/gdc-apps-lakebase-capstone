"""App-runtime configuration (pydantic-settings).

The app runs in two environments:

  * **Deployed** on Databricks Apps — the runtime injects real env vars
    (``PGHOST``, ``LAKEBASE_ENDPOINT``, the service-principal OAuth creds
    ``DATABRICKS_CLIENT_ID`` / ``DATABRICKS_CLIENT_SECRET``, …). There is no
    ``.env`` file.
  * **Local dev** — no injected vars; config comes from ``app/.env`` and the
    client authenticates via ``DATABRICKS_PROFILE``.

**Source priority is inverted from the pydantic-settings default.** Normally
process env vars outrank the ``.env`` file; here ``.env`` wins. That's
deliberate: a local ``.env`` authoritatively configures dev, so an ambient
``DATABRICKS_PROFILE=default`` on the developer's machine can't clobber the
``fevm-test-jg`` profile. When deployed there is no ``.env``, so the injected
env vars are used as intended.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

# app/backend/config.py -> app/.env
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """Typed capstone config. Field names map case-insensitively to env keys."""

    model_config = SettingsConfigDict(
        env_file=_ENV_PATH,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    databricks_profile: str = "DEFAULT"
    databricks_host: str
    lakebase_endpoint: str

    # Warehouse + gold catalog for the metrics endpoint (warehouse + OBO path).
    warehouse_id: str
    capstone_catalog: str
    capstone_schema: str = "gold"

    pghost: str
    pgport: int = 5432
    pgdatabase: str
    pguser: str | None = None

    # Presence of the SP client id means the runtime injected creds -> deployed.
    databricks_client_id: str | None = None

    # Embed / Genie ids (T4 config endpoint; genie_space_id reused by T5).
    dashboard_id: str | None = None
    genie_space_id: str | None = None

    # Forward-ETL job id (bundle-injected via the app `job` resource, T7/T8).
    forward_etl_job_id: str | None = None

    @property
    def deployed(self) -> bool:
        """True when running on Databricks Apps (SP creds are injected)."""
        return self.databricks_client_id is not None

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # .env outranks process env vars (see module docstring).
        return init_settings, dotenv_settings, env_settings, file_secret_settings


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()
