# T5 — Genie chat integration — design

**Date:** 2026-08-09
**Task:** CAPSTONE_TASKS.md T5 ("Integrate Genie chat")
**Stacked on:** t4 → t3-frontend → t3-backend → …

## Goal

Let reps ask ad-hoc natural-language questions inside the app ("which segments
saw declining LTV in Q3?", "which EU customers have churn > 0.7?"), answered by
the Databricks **Genie Conversation API** over the provisioned Genie space,
rendered as a floating chat overlay.

## Decisions (locked in brainstorm)

- **Answer rendering:** text answer **+ compact table preview** when the message
  carries a query attachment (first ~10 rows). No collapsible SQL block.
- **Poll model:** client-side poll loop against three thin endpoints (task-literal),
  not the SDK's `_and_wait` variants — keeps each request short.
- **Chat state:** in-memory, single conversation for the session. Follow-ups reuse
  the `conversation_id` (satisfies "maintains context"); a "New chat" button resets;
  a full page reload starts fresh (no localStorage).

## Backend — `app/backend/routers/genie.py`

Three endpoints, all OBO (calling user via the existing `Obo` dependency).
`space_id` = `settings.genie_space_id` (added to `Settings` in T4). SDK surface is
`obo.genie.*`; blocking calls wrapped in `asyncio.to_thread` (consistent with the
metrics/dashboard endpoints). Router registered in `main.py` after `dashboard`,
before the SPA catch-all.

| Method + Path | Body | SDK call | Returns |
|---|---|---|---|
| `POST /api/genie/conversations` | `{content}` | `genie.start_conversation(space_id, content)` | `{conversation_id, message_id}` |
| `POST /api/genie/conversations/{cid}/messages` | `{content}` | `genie.create_message(space_id, cid, content)` | `{message_id}` |
| `GET /api/genie/conversations/{cid}/messages/{mid}` | — | `genie.get_message(space_id, cid, mid)` (+ attachment result when terminal) | `GenieMessageOut` |

**Request models:** `GenieStart{ content: str }`, `GenieFollowUp{ content: str }`.

**`GenieMessageOut` (Pydantic response model):**
- `status: str` — from `MessageStatus` enum (`SUBMITTED`, `FILTERING_CONTEXT`,
  `ASKING_AI`, `PENDING_WAREHOUSE`, `EXECUTING_QUERY`, `FETCHING_METADATA`,
  `COMPLETED`, `FAILED`, `CANCELLED`, `QUERY_RESULT_EXPIRED`). Terminal set the
  client stops on: `COMPLETED`, `FAILED`, `CANCELLED`, `QUERY_RESULT_EXPIRED`.
- `text: str | None` — natural-language answer from the first attachment's
  `text.content` (fall back to message `content` if present).
- `result: GenieResult | None` — present only when an attachment has a `query`
  AND status is `COMPLETED`. `GenieResult{ columns: list[str], rows: list[list] }`
  built from the attachment query result's
  `statement_response.manifest.schema.columns[].name` +
  `statement_response.result.data_array` (rows capped server-side at ~50; the UI
  shows ~10).
- `error: str | None` — from `message.error` when status is `FAILED`.

**GET handler flow:** call `get_message`; map `status`. If terminal `COMPLETED`
and `attachments[0].query` is set, call
`genie.get_message_attachment_query_result(space_id, cid, mid, attachment_id)` and
map its `statement_response` into `GenieResult`. If no query attachment, return
text only. Never raise on `FAILED` — return the `error` field so the UI can show a
caution, not a 500. (Missing OBO header still raises `PermissionError` → 401 via
the existing handler.)

## Frontend

### `GenieWidget.tsx` — floating overlay mounted in `AppShell`
Mounted once in `AppShell` (not a route), floats over every page. Uses the `Radio`
lucide icon already imported in AppShell (cockpit "comms channel" idiom).

- **Closed:** bottom-right anchored "Ask Genie" button (radio-green, hover glow).
- **Open (compact):** panel with scrollable transcript + input + send button.
  Header carries an **Enlarge toggle** (compact ↔ wide) and a **"New chat"** reset.
  The wide header adds an **"Open in workspace"** deep-link to
  `${databricks_host}/genie/rooms/${genie_space_id}` (both from `useConfig()`).
- **Messages:** user bubbles + Genie bubbles. A Genie answer renders its `text`,
  then — when `result` is present — a compact cockpit table (first ~10 rows,
  wrapped in `overflow-x-auto`). Bezel/face/lum tokens, JetBrains Mono for the table.

### Data flow — client poll loop
- **Send:** first message → `POST /conversations` → `{conversation_id, message_id}`;
  follow-ups → `POST /conversations/{cid}/messages` → `{message_id}`.
  `conversation_id` + transcript held in React state.
- **Poll:** after each send, poll `GET .../messages/{mid}` (~1.2s interval) until
  `status` terminal, **capped at ~30s**. Typing indicator while polling.
  Implemented with `useQuery` + `refetchInterval` that returns `false` on terminal
  status (or a small `setInterval` loop) plus a wall-clock cap.
- **api.ts:** `api.genie.start(content)`, `api.genie.followUp(cid, content)`,
  `api.genie.getMessage(cid, mid)`. **types.ts:** `GenieMessageOut`, `GenieResult`.
  **queries.ts:** a `useGenieMessage(cid, mid, enabled)` polling query + plain
  mutation helpers for the two POSTs (or call `api.genie.*` directly from the widget).

### Error & edge states (night-flight voice)
- **Timeout** (30s no terminal): stop polling, amber caution line + retry.
- **`FAILED`/`error`:** render Genie's error text in an amber caution bubble
  (reuse the `tone="caution"` idiom), not a red crash.
- **No OBO locally:** endpoints 401 without a token (same caveat as metrics/dashboard);
  the widget shows a caution state on send. Works live on deploy.
- **Empty/no-attachment answer:** render text only.

## Testing

- **Backend `tests/test_t5_genie.py`:**
  - `live`-marked: start a conversation ("Which segment has the highest average
    lifetime value?"), poll `get_message` to a terminal status, assert a non-empty
    `text` answer. Skips without Databricks auth (conftest `live` gate). Mirrors the
    T3/T4 live-test pattern; OBO overridden to the SP client in the fixture.
  - non-live: assert the routes exist and missing OBO → 401 (dependency-override off
    → `PermissionError` path). (If asserting 401 cleanly is awkward with the SP
    override fixture, assert route registration via the OpenAPI schema instead.)
- **Frontend:** `bunx tsc --noEmit` + `bun run build` green (no unit-test harness
  in this project).

## Files

- Create: `app/backend/routers/genie.py`, `app/tests/test_t5_genie.py`,
  `app/frontend/src/components/GenieWidget.tsx`.
- Modify: `app/backend/main.py` (register router),
  `app/frontend/src/components/AppShell.tsx` (mount `<GenieWidget/>`),
  `app/frontend/src/lib/{api,types,queries}.ts`.

## Explicitly NOT doing

- No `_and_wait` server-blocking variants; no SQL block in the UI; no localStorage
  persistence; no message feedback/thumbs; no multi-conversation history list; no
  visualization/`viz` rendering (table preview only). These are beyond the task's
  two "Done when" criteria.

## Done when (from task)

- "Top segment by LTV" returns an answer **+ a result preview**.
- Follow-up questions in the same conversation **maintain context**
  (reuse `conversation_id`).

## Verify

- `POST /api/genie/conversations` returns ids; `GET .../messages/{mid}` polls to
  `COMPLETED` with `text` (+ `result` for a table question) — via curl with an
  injected OBO token, or the live test.
- Widget: ask a question → typing indicator → answer + table; ask a follow-up →
  context retained; Enlarge + "Open in workspace" + "New chat" work.
- ruff format + check clean; `tsc --noEmit` + `bun run build` clean.
