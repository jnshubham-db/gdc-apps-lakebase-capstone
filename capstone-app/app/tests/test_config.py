"""Config tests — pydantic-settings source priority.

The one behaviour worth locking down: ``app/.env`` outranks process env vars,
so an ambient ``DATABRICKS_PROFILE`` on a dev machine can't clobber the value
in ``.env``. (This is the inverted source order in ``config.Settings``.)
"""

from __future__ import annotations

from backend.config import Settings


def test_dotenv_outranks_ambient_env(monkeypatch):
    monkeypatch.setenv("DATABRICKS_PROFILE", "ambient-should-lose")
    settings = Settings()  # fresh instance, not the cached one
    assert settings.databricks_profile == "fevm-test-jg"


def test_deployed_flag_follows_sp_creds(monkeypatch):
    monkeypatch.delenv("DATABRICKS_CLIENT_ID", raising=False)
    assert Settings().deployed is False
