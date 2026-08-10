"""Genie conversation endpoints (T5).

Three thin OBO endpoints wrap the Genie Conversation API. start/follow-up return
immediately with ids (the SDK's ``Wait`` exposes them without blocking); the
client polls GET until the message reaches a terminal status. When a completed
message carries a query attachment, the GET handler also fetches the attachment
query result and returns a compact table preview.
"""

from __future__ import annotations

import asyncio

from databricks.sdk import WorkspaceClient
from fastapi import APIRouter
from pydantic import BaseModel

from ..config import get_settings
from ..deps import Obo

router = APIRouter(prefix="/api/genie", tags=["genie"])

_ROW_CAP = 50  # server-side cap on preview rows (UI shows ~10)


class GenieStart(BaseModel):
    content: str


class GenieFollowUp(BaseModel):
    content: str


class GenieResult(BaseModel):
    columns: list[str]
    rows: list[list]


class GenieMessageOut(BaseModel):
    status: str
    text: str | None = None
    result: GenieResult | None = None
    error: str | None = None


def _start(w: WorkspaceClient, content: str) -> dict:
    s = get_settings()
    wait = w.genie.start_conversation(s.genie_space_id, content)
    return {"conversation_id": wait.conversation_id, "message_id": wait.message_id}


def _follow_up(w: WorkspaceClient, cid: str, content: str) -> dict:
    s = get_settings()
    wait = w.genie.create_message(s.genie_space_id, cid, content)
    return {"message_id": wait.message_id}


def _text_of(msg) -> str | None:
    for att in msg.attachments or []:
        if att.text and att.text.content:
            return att.text.content
    return msg.content or None


def _fetch(w: WorkspaceClient, cid: str, mid: str) -> GenieMessageOut:
    s = get_settings()
    msg = w.genie.get_message(s.genie_space_id, cid, mid)
    status = msg.status.value if msg.status else "UNKNOWN"
    out = GenieMessageOut(status=status, text=_text_of(msg))

    if msg.error:
        out.error = getattr(msg.error, "error", None) or str(msg.error)

    if status == "COMPLETED":
        query_att = next((a for a in (msg.attachments or []) if a.query), None)
        if query_att:
            qr = w.genie.get_message_attachment_query_result(
                s.genie_space_id, cid, mid, query_att.attachment_id
            )
            sr = qr.statement_response
            if sr and sr.manifest and sr.result:
                cols = [c.name for c in (sr.manifest.schema.columns or [])]
                data = sr.result.data_array or []
                out.result = GenieResult(columns=cols, rows=data[:_ROW_CAP])
    return out


@router.post("/conversations")
async def start_conversation(body: GenieStart, obo: Obo) -> dict:
    return await asyncio.to_thread(_start, obo, body.content)


@router.post("/conversations/{cid}/messages")
async def create_message(cid: str, body: GenieFollowUp, obo: Obo) -> dict:
    return await asyncio.to_thread(_follow_up, obo, cid, body.content)


@router.get("/conversations/{cid}/messages/{mid}", response_model=GenieMessageOut)
async def get_message(cid: str, mid: str, obo: Obo) -> GenieMessageOut:
    return await asyncio.to_thread(_fetch, obo, cid, mid)
