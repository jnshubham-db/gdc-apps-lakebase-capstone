"""T2 — Two identities for the app.

* **OBO** (on-behalf-of) — ``obo_client(request)`` carries the *calling
  user's* identity to the SQL warehouse and Genie, so workspace RLS and
  audit attribute to the human. Built from the ``X-Forwarded-Access-Token``
  header the Databricks Apps runtime injects (requires the workspace's
  "User authorization" preview + a one-time per-user consent).

* **SP** (service principal) — ``sp_client()`` is the app's own identity,
  used for **all Lakebase access** (see ``db.py``) and the forward-ETL job
  trigger. Not tied to any user.

There is deliberately **no ``lakebase_obo()``**: Lakebase rejects a user OBO
bearer with ``Provided OAuth token does not have required scopes: postgres``
— OBO scopes don't yet cover Postgres. So every DB read/write runs as the SP,
and the human is recorded separately via ``actor_email(request)`` for audit.

OBO scopes for this capstone are exactly ``sql`` (warehouse) and
``dashboards.genie`` (Genie); wired into ``app.yaml`` in T6.
"""

from __future__ import annotations

from databricks.sdk import WorkspaceClient

from .config import get_settings

_ACCESS_TOKEN_HEADER = "X-Forwarded-Access-Token"
_EMAIL_HEADER = "X-Forwarded-Email"

_sp: WorkspaceClient | None = None


def sp_client() -> WorkspaceClient:
    """The app service-principal client (lazy module-level singleton).

    Deployed: the runtime injects SP OAuth creds, so a bare ``WorkspaceClient``
    authenticates as the SP. Local: fall back to the configured CLI profile,
    which connects as the developer — enough to exercise Lakebase + Genie
    before the app (and its SP) is deployed.
    """
    global _sp
    if _sp is None:
        settings = get_settings()
        _sp = (
            WorkspaceClient()
            if settings.deployed
            else WorkspaceClient(profile=settings.databricks_profile)
        )
    return _sp


def obo_client(request) -> WorkspaceClient:
    """A WorkspaceClient acting as the calling user (SQL warehouse + Genie).

    Reads the ``X-Forwarded-Access-Token`` the runtime injects per request.
    Raises if absent — which means the workspace OBO preview is off or the
    user hasn't completed the one-time consent.
    """
    token = request.headers.get(_ACCESS_TOKEN_HEADER)
    if not token:
        raise PermissionError(
            f"{_ACCESS_TOKEN_HEADER} missing — enable the workspace 'User "
            "authorization' preview and complete the per-user consent."
        )
    return WorkspaceClient(host=get_settings().databricks_host, token=token)


def actor_email(request) -> str:
    """Email of the calling user, for the audit log.

    From the ``X-Forwarded-Email`` header when deployed; locally there is no
    such header, so fall back to the identity ``sp_client()`` authenticates as
    (the developer).
    """
    return request.headers.get(_EMAIL_HEADER) or sp_client().current_user.me().user_name
