# T4 — Analytics Dashboard (Native Rebuild) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `/dashboard` placeholder with a native cockpit-themed analytics page that rebuilds the five provisioned AI/BI dashboard charts using Recharts, backed by two new FastAPI endpoints.

**Architecture:** A new `dashboard` router exposes `GET /api/config` (static workspace ids, TTL-cached) and `GET /api/dashboard/analytics` (four gold-table aggregates run on the SQL warehouse via OBO, fanned out with `asyncio.gather`, TTL-cached). The React page fetches both through TanStack Query and renders five night-flight-themed Recharts panels, with an "Open in AI/BI workspace" deep-link that preserves the Lakeview-embed skill on record.

**Tech Stack:** FastAPI, Databricks SDK (`statement_execution`), `cachetools`, Pydantic; React 18, TanStack Query, Recharts, Tailwind (night-flight tokens), TypeScript.

## Global Constraints

- Python: ruff-clean (`uvx ruff format app/ lakebase/` + `uvx ruff check --fix app/ lakebase/`), `line-length = 100`, `target-version = py311`. Both must pass before commit.
- Pytest runs **from `app/`**; live-marked tests skip without Databricks auth. Marker: `pytestmark = pytest.mark.live` for tests hitting the warehouse.
- Warehouse queries use **OBO** (`Obo` dep = calling user's `X-Forwarded-Access-Token`). Missing header → `PermissionError` → 401 (handled in `main.py`).
- Warehouse settings come from `Settings`: `warehouse_id`, `capstone_catalog`, `capstone_schema` (default `"gold"`).
- Frontend `@/*` path alias → `frontend/src/*`. Installs via `bun`.
- Fully-qualified table refs are unnecessary in warehouse calls — `_run_stmt` passes `catalog`/`schema`, so SQL uses bare `customers`, `transactions`, etc. (matching the existing metrics SQL).
- No secrets or ids are hardcoded in source — they come from `Settings` / `.env`.

---

## File Structure

**Backend**
- Modify `app/backend/config.py` — add `dashboard_id`, `genie_space_id` fields.
- Create `app/backend/routers/dashboard.py` — `/api/config` + `/api/dashboard/analytics`, SQL constants, models, TTL caches, `_run_sql` helper.
- Modify `app/backend/main.py` — register the dashboard router.
- Modify `app/pyproject.toml` — add `cachetools` dependency.
- Create `app/tests/test_t4_dashboard.py` — endpoint tests.

**Frontend**
- Modify `app/frontend/src/lib/types.ts` — add `AppConfig`, `SegmentAgg`, `ProductRevenue`, `TicketPoint`, `ChurnBucket`, `DashboardAnalytics`.
- Modify `app/frontend/src/lib/api.ts` — add `getConfig`, `getDashboardAnalytics`.
- Modify `app/frontend/src/lib/queries.ts` — add `useConfig`, `useDashboardAnalytics`.
- Create `app/frontend/src/components/charts.tsx` — cockpit-themed Recharts wrappers (bar / multi-line / histogram) + shared tooltip/axis styling.
- Create `app/frontend/src/pages/Dashboard.tsx` — the page: 5 panels + header deep-link + states.
- Modify `app/frontend/src/main.tsx` — swap the dashboard `ComingSoon` for the lazy `Dashboard`.
- Modify `app/package.json` — add `recharts`.

---

### Task 1: Config endpoint (`/api/config`)

**Files:**
- Modify: `app/backend/config.py`
- Create: `app/backend/routers/dashboard.py`
- Modify: `app/backend/main.py`
- Modify: `app/pyproject.toml`
- Test: `app/tests/test_t4_dashboard.py`

**Interfaces:**
- Consumes: `Settings` (`get_settings`), `SettingsDep` alias from `deps.py`.
- Produces:
  - `Settings.dashboard_id: str | None`, `Settings.genie_space_id: str | None`.
  - `router = APIRouter(prefix="/api", tags=["dashboard"])` in `dashboard.py`.
  - `GET /api/config` → `AppConfig{ databricks_host: str, dashboard_id: str | None, genie_space_id: str | None }`.

- [ ] **Step 1: Add config fields**

In `app/backend/config.py`, after the `databricks_client_id` field (line ~60), add:

```python
    # Embed / Genie ids (T4 config endpoint; genie_space_id reused by T5).
    dashboard_id: str | None = None
    genie_space_id: str | None = None
```

- [ ] **Step 2: Add cachetools dependency**

In `app/pyproject.toml`, inside the `dependencies = [` list, add:

```toml
    "cachetools>=5.3",
```

- [ ] **Step 3: Create the dashboard router with `/api/config`**

Create `app/backend/routers/dashboard.py`:

```python
"""Analytics dashboard + app-config endpoints (T4).

``/api/config`` exposes the static workspace ids the frontend needs (host +
dashboard + Genie space). ``/api/dashboard/analytics`` recomputes the five
provisioned AI/BI charts natively: four gold-table aggregates run on the SQL
warehouse via OBO (the calling rep's identity), fanned out and TTL-cached.

SQL lives in named constants below the handlers, mirroring the customers router.
"""

from __future__ import annotations

import asyncio

from cachetools import TTLCache
from databricks.sdk import WorkspaceClient
from fastapi import APIRouter
from pydantic import BaseModel

from ..config import get_settings
from ..deps import Obo, SettingsDep

router = APIRouter(prefix="/api", tags=["dashboard"])


class AppConfig(BaseModel):
    databricks_host: str
    dashboard_id: str | None = None
    genie_space_id: str | None = None


@router.get("/config", response_model=AppConfig)
async def get_config(settings: SettingsDep) -> AppConfig:
    return AppConfig(
        databricks_host=settings.databricks_host,
        dashboard_id=settings.dashboard_id,
        genie_space_id=settings.genie_space_id,
    )
```

- [ ] **Step 4: Register the router**

In `app/backend/main.py`, alongside the existing customers import/include:

```python
from .routers import customers, dashboard
```
```python
app.include_router(customers.router)
app.include_router(dashboard.router)
```

Note: `dashboard.router` already carries the `/api` prefix; the SPA catch-all `@app.get("/{full_path:path}")` is registered after routers so `/api/*` is matched first.

- [ ] **Step 5: Write the config test**

Create `app/tests/test_t4_dashboard.py`:

```python
"""T4 endpoint tests via FastAPI TestClient.

Config is static (no auth); analytics hits the warehouse via OBO, overridden
to the SP client for the test, so those carry the ``live`` marker.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.deps import get_obo_client
from backend.main import app


@pytest.fixture
def client():
    from backend.auth import sp_client

    app.dependency_overrides[get_obo_client] = sp_client  # warehouse as SP for the test
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_config_shape(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"databricks_host", "dashboard_id", "genie_space_id"}
    assert body["databricks_host"].startswith("http")
```

- [ ] **Step 6: Run the config test**

Run:
```bash
cd app && uv run --with "psycopg[binary,pool]" --with databricks-sdk \
    --with python-dotenv --with pytest --with cachetools \
    pytest tests/test_t4_dashboard.py::test_config_shape -v
```
Expected: PASS (this test is not `live`-marked, runs without Databricks auth as long as `.env` provides `databricks_host`).

- [ ] **Step 7: ruff + commit**

```bash
uvx ruff format app/ && uvx ruff check --fix app/
git add app/backend/config.py app/backend/routers/dashboard.py app/backend/main.py \
    app/pyproject.toml app/tests/test_t4_dashboard.py
git commit -m "feat(t4): add /api/config endpoint"
```

---

### Task 2: Analytics endpoint (`/api/dashboard/analytics`)

**Files:**
- Modify: `app/backend/routers/dashboard.py`
- Test: `app/tests/test_t4_dashboard.py`

**Interfaces:**
- Consumes: `Obo` (calling user's `WorkspaceClient`), `get_settings()`.
- Produces: `GET /api/dashboard/analytics` → `DashboardAnalytics`:
  - `segments: list[SegmentAgg]` — `segment_name: str, customers: int, avg_ltv: float, avg_churn: float`
  - `products: list[ProductRevenue]` — `product_name: str, category: str, revenue: float, units: int`
  - `tickets: list[TicketPoint]` — `week: str, category: str, tickets: int`
  - `churn_buckets: list[ChurnBucket]` — `bucket: float, customers: int`

- [ ] **Step 1: Write the failing analytics test**

Append to `app/tests/test_t4_dashboard.py`:

```python
pytestmark = pytest.mark.live  # applies to tests defined below via module marker


def test_analytics_shape(client):
    r = client.get("/api/dashboard/analytics")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"segments", "products", "tickets", "churn_buckets"}
    assert len(body["segments"]) >= 1
    assert {"segment_name", "customers", "avg_ltv", "avg_churn"} <= set(body["segments"][0])
    assert len(body["products"]) <= 15
    assert all(0.0 <= b["bucket"] <= 1.0 for b in body["churn_buckets"])
```

Note: `pytest.mark.live` set as a module-level `pytestmark` marks **all** tests in the file. Since `test_config_shape` should still run without auth, do NOT use a module-level marker — instead decorate this test individually. Replace the two lines above with:

```python
@pytest.mark.live
def test_analytics_shape(client):
    r = client.get("/api/dashboard/analytics")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"segments", "products", "tickets", "churn_buckets"}
    assert len(body["segments"]) >= 1
    assert {"segment_name", "customers", "avg_ltv", "avg_churn"} <= set(body["segments"][0])
    assert len(body["products"]) <= 15
    assert all(0.0 <= b["bucket"] <= 1.0 for b in body["churn_buckets"])
```

- [ ] **Step 2: Run to verify it fails**

Run:
```bash
cd app && uv run --with "psycopg[binary,pool]" --with databricks-sdk \
    --with python-dotenv --with pytest --with cachetools \
    pytest tests/test_t4_dashboard.py::test_analytics_shape -v
```
Expected: FAIL with 404 (route not defined) — or SKIP if no Databricks auth. If it skips, proceed; the shape is exercised on a credentialed machine.

- [ ] **Step 3: Add models, helper, cache, handler, and SQL**

In `app/backend/routers/dashboard.py`, add the models below `AppConfig`:

```python
class SegmentAgg(BaseModel):
    segment_name: str
    customers: int
    avg_ltv: float
    avg_churn: float


class ProductRevenue(BaseModel):
    product_name: str
    category: str
    revenue: float
    units: int


class TicketPoint(BaseModel):
    week: str
    category: str
    tickets: int


class ChurnBucket(BaseModel):
    bucket: float
    customers: int


class DashboardAnalytics(BaseModel):
    segments: list[SegmentAgg]
    products: list[ProductRevenue]
    tickets: list[TicketPoint]
    churn_buckets: list[ChurnBucket]


# Slow-changing org-wide analytics — cache the whole payload for 5 min.
_analytics_cache: TTLCache = TTLCache(maxsize=1, ttl=300)
```

Add the warehouse helper (param-less sibling of the customers router's `_run_stmt`):

```python
def _run_sql(w: WorkspaceClient, sql: str) -> list[dict]:
    """Run one param-less warehouse statement, return rows as dicts."""
    s = get_settings()
    resp = w.statement_execution.execute_statement(
        statement=sql,
        warehouse_id=s.warehouse_id,
        catalog=s.capstone_catalog,
        schema=s.capstone_schema,
        wait_timeout="30s",
    )
    cols = [c.name for c in (resp.manifest.schema.columns or [])]
    data = resp.result.data_array if resp.result and resp.result.data_array else []
    return [dict(zip(cols, row)) for row in data]
```

Add the handler:

```python
@router.get("/dashboard/analytics", response_model=DashboardAnalytics)
async def dashboard_analytics(obo: Obo) -> DashboardAnalytics:
    if "payload" in _analytics_cache:
        return _analytics_cache["payload"]

    segments, products, tickets, churn = await asyncio.gather(
        asyncio.to_thread(_run_sql, obo, _Q_SEGMENTS),
        asyncio.to_thread(_run_sql, obo, _Q_PRODUCTS),
        asyncio.to_thread(_run_sql, obo, _Q_TICKETS),
        asyncio.to_thread(_run_sql, obo, _Q_CHURN),
    )

    payload = DashboardAnalytics(
        segments=[
            SegmentAgg(
                segment_name=r["segment_name"],
                customers=int(r["customers"]),
                avg_ltv=float(r["avg_ltv"]),
                avg_churn=float(r["avg_churn"]),
            )
            for r in segments
        ],
        products=[
            ProductRevenue(
                product_name=r["product_name"],
                category=r["category"],
                revenue=float(r["revenue"]),
                units=int(r["units"]),
            )
            for r in products
        ],
        tickets=[
            TicketPoint(week=str(r["week"]), category=r["category"], tickets=int(r["tickets"]))
            for r in tickets
        ],
        churn_buckets=[
            ChurnBucket(bucket=float(r["bucket"]), customers=int(r["customers"]))
            for r in churn
        ],
    )
    _analytics_cache["payload"] = payload
    return payload
```

Add the SQL constants at the bottom of the file (verbatim from the provisioned dashboard datasets, catalog/schema stripped since `_run_sql` passes them):

```python
_Q_SEGMENTS = (
    "SELECT s.segment_name, COUNT(*) AS customers, "
    "ROUND(AVG(c.lifetime_value), 2) AS avg_ltv, "
    "ROUND(AVG(c.churn_score), 3) AS avg_churn "
    "FROM customers c JOIN customer_segments s ON c.segment_id = s.segment_id "
    "GROUP BY s.segment_name ORDER BY avg_ltv DESC"
)

_Q_PRODUCTS = (
    "SELECT p.name AS product_name, p.category, "
    "ROUND(SUM(t.amount), 2) AS revenue, COUNT(*) AS units "
    "FROM transactions t JOIN products p ON t.product_id = p.product_id "
    "WHERE t.status = 'completed' "
    "GROUP BY p.name, p.category ORDER BY revenue DESC LIMIT 15"
)

_Q_TICKETS = (
    "SELECT DATE_TRUNC('week', opened_at) AS week, category, COUNT(*) AS tickets "
    "FROM support_tickets "
    "GROUP BY DATE_TRUNC('week', opened_at), category ORDER BY week"
)

_Q_CHURN = (
    "SELECT ROUND(FLOOR(churn_score * 10) / 10, 1) AS bucket, COUNT(*) AS customers "
    "FROM customers "
    "GROUP BY ROUND(FLOOR(churn_score * 10) / 10, 1) ORDER BY bucket"
)
```

- [ ] **Step 4: Run the analytics test**

Run:
```bash
cd app && uv run --with "psycopg[binary,pool]" --with databricks-sdk \
    --with python-dotenv --with pytest --with cachetools \
    pytest tests/test_t4_dashboard.py -v
```
Expected: `test_config_shape` PASS; `test_analytics_shape` PASS on a credentialed machine (SKIP otherwise).

- [ ] **Step 5: ruff + commit**

```bash
uvx ruff format app/ && uvx ruff check --fix app/
git add app/backend/routers/dashboard.py app/tests/test_t4_dashboard.py
git commit -m "feat(t4): add /api/dashboard/analytics warehouse aggregates"
```

---

### Task 3: Frontend data layer (types, api, queries)

**Files:**
- Modify: `app/frontend/src/lib/types.ts`
- Modify: `app/frontend/src/lib/api.ts`
- Modify: `app/frontend/src/lib/queries.ts`

**Interfaces:**
- Consumes: existing `request<T>` wrapper in `api.ts`, `api` object, `useQuery` from TanStack.
- Produces:
  - Types: `AppConfig`, `SegmentAgg`, `ProductRevenue`, `TicketPoint`, `ChurnBucket`, `DashboardAnalytics`.
  - `api.getConfig(): Promise<AppConfig>`, `api.getDashboardAnalytics(): Promise<DashboardAnalytics>`.
  - `useConfig()` (staleTime 5m), `useDashboardAnalytics()` (staleTime 60s, retry 1).

- [ ] **Step 1: Add types**

Append to `app/frontend/src/lib/types.ts`:

```typescript
export interface AppConfig {
  databricks_host: string;
  dashboard_id: string | null;
  genie_space_id: string | null;
}

export interface SegmentAgg {
  segment_name: string;
  customers: number;
  avg_ltv: number;
  avg_churn: number;
}

export interface ProductRevenue {
  product_name: string;
  category: string;
  revenue: number;
  units: number;
}

export interface TicketPoint {
  week: string;
  category: string;
  tickets: number;
}

export interface ChurnBucket {
  bucket: number;
  customers: number;
}

export interface DashboardAnalytics {
  segments: SegmentAgg[];
  products: ProductRevenue[];
  tickets: TicketPoint[];
  churn_buckets: ChurnBucket[];
}
```

- [ ] **Step 2: Add api methods**

In `app/frontend/src/lib/api.ts`, extend the import type list with `AppConfig` and `DashboardAnalytics`, then add to the `api` object:

```typescript
  getConfig: () => request<AppConfig>("/config"),

  getDashboardAnalytics: () => request<DashboardAnalytics>("/dashboard/analytics"),
```

- [ ] **Step 3: Add queries**

Append to `app/frontend/src/lib/queries.ts`:

```typescript
export function useConfig() {
  return useQuery({
    queryKey: ["config"] as const,
    queryFn: () => api.getConfig(),
    staleTime: 5 * 60_000,
  });
}

export function useDashboardAnalytics() {
  return useQuery({
    queryKey: ["dashboard", "analytics"] as const,
    queryFn: () => api.getDashboardAnalytics(),
    staleTime: 60_000,
    retry: 1,
  });
}
```

- [ ] **Step 4: Typecheck**

Run:
```bash
cd app && bunx tsc --noEmit -p tsconfig.json
```
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add app/frontend/src/lib/types.ts app/frontend/src/lib/api.ts app/frontend/src/lib/queries.ts
git commit -m "feat(t4): frontend data layer for config + dashboard analytics"
```

---

### Task 4: Chart components + Dashboard page + route

**Files:**
- Modify: `app/package.json` (add `recharts`)
- Create: `app/frontend/src/components/charts.tsx`
- Create: `app/frontend/src/pages/Dashboard.tsx`
- Modify: `app/frontend/src/main.tsx`

**Interfaces:**
- Consumes: `useConfig`, `useDashboardAnalytics` (Task 3); `Panel`, `PanelHeader` (`components/ui.tsx`); `RouteFallback`, `Skeleton`, `EmptyState`, `ErrorState` (`components/states.tsx`); `segmentName` (`lib/segments.ts`); `usd` (`lib/utils.ts`); night-flight tokens (`green #39FF9A`, `amber #FFB000`, `alert #FF3B30`, `muted #6B7580`, `lum #F2F5F2`, `bezel`, `face`).
- Produces: default-exported `Dashboard` page component; themed chart wrappers `SegmentLtvChart`, `SegmentChurnChart`, `TopProductsChart`, `TicketsTrendChart`, `ChurnDistributionChart`.

- [ ] **Step 1: Install recharts**

Run:
```bash
cd app && bun add recharts
```
Expected: `recharts` added to `package.json` dependencies.

- [ ] **Step 2: Create themed chart components**

Create `app/frontend/src/components/charts.tsx`. Cockpit-themed Recharts wrappers. Palette constants inline (Recharts needs literal colors, not Tailwind classes). Amber/alert are used semantically: churn rises amber→alert; the 0.8+ churn buckets render alert.

```tsx
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { segmentName } from "@/lib/segments";
import type { ChurnBucket, ProductRevenue, SegmentAgg, TicketPoint } from "@/lib/types";
import { usd } from "@/lib/utils";

const GREEN = "#39FF9A";
const AMBER = "#FFB000";
const ALERT = "#FF3B30";
const MUTED = "#6B7580";
const GRID = "#1A1E22"; // bezel
const FACE = "#111417";
const LUM = "#F2F5F2";

const AXIS = { stroke: MUTED, fontSize: 11, fontFamily: "'JetBrains Mono', monospace" } as const;

/** Shared dark tooltip in the panel idiom. */
function tip(formatter?: (v: number) => string) {
  return (
    <Tooltip
      cursor={{ fill: "rgba(255,255,255,0.04)" }}
      contentStyle={{
        background: FACE,
        border: `1px solid ${GRID}`,
        borderRadius: 2,
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 12,
        color: LUM,
      }}
      labelStyle={{ color: MUTED }}
      formatter={formatter ? (v: number) => formatter(v) : undefined}
    />
  );
}

const H = 260;

export function SegmentLtvChart({ data }: { data: SegmentAgg[] }) {
  return (
    <ResponsiveContainer width="100%" height={H}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="segment_name" tick={AXIS} axisLine={{ stroke: GRID }} tickLine={false}
          interval={0} angle={-30} textAnchor="end" height={70} />
        <YAxis tick={AXIS} axisLine={{ stroke: GRID }} tickLine={false}
          tickFormatter={(v) => usd(v)} width={70} />
        {tip((v) => usd(v))}
        <Bar dataKey="avg_ltv" fill={GREEN} radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function SegmentChurnChart({ data }: { data: SegmentAgg[] }) {
  return (
    <ResponsiveContainer width="100%" height={H}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="segment_name" tick={AXIS} axisLine={{ stroke: GRID }} tickLine={false}
          interval={0} angle={-30} textAnchor="end" height={70} />
        <YAxis tick={AXIS} axisLine={{ stroke: GRID }} tickLine={false} domain={[0, 1]} width={40} />
        {tip((v) => v.toFixed(3))}
        <Bar dataKey="avg_churn" radius={[2, 2, 0, 0]}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.avg_churn >= 0.7 ? ALERT : d.avg_churn >= 0.4 ? AMBER : GREEN} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function TopProductsChart({ data }: { data: ProductRevenue[] }) {
  return (
    <ResponsiveContainer width="100%" height={H}>
      <BarChart data={data} layout="vertical" margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" tick={AXIS} axisLine={{ stroke: GRID }} tickLine={false}
          tickFormatter={(v) => usd(v)} />
        <YAxis type="category" dataKey="product_name" tick={AXIS} axisLine={{ stroke: GRID }}
          tickLine={false} width={140} interval={0} />
        {tip((v) => usd(v))}
        <Bar dataKey="revenue" fill={GREEN} radius={[0, 2, 2, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

const TICKET_TONE: Record<string, string> = {
  billing: ALERT,
  returns: AMBER,
  shipping: GREEN,
};

export function TicketsTrendChart({ data }: { data: TicketPoint[] }) {
  // Pivot long rows → one point per week with a column per category.
  const byWeek = new Map<string, Record<string, number | string>>();
  const cats = new Set<string>();
  for (const r of data) {
    cats.add(r.category);
    const wk = r.week.slice(0, 10);
    const row = byWeek.get(wk) ?? { week: wk };
    row[r.category] = r.tickets;
    byWeek.set(wk, row);
  }
  const rows = [...byWeek.values()].sort((a, b) => String(a.week).localeCompare(String(b.week)));
  const categories = [...cats];

  return (
    <ResponsiveContainer width="100%" height={H}>
      <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="week" tick={AXIS} axisLine={{ stroke: GRID }} tickLine={false}
          minTickGap={40} />
        <YAxis tick={AXIS} axisLine={{ stroke: GRID }} tickLine={false} width={40} />
        {tip()}
        {categories.map((c) => (
          <Line key={c} type="monotone" dataKey={c} stroke={TICKET_TONE[c] ?? MUTED}
            strokeWidth={1.75} dot={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function ChurnDistributionChart({ data }: { data: ChurnBucket[] }) {
  return (
    <ResponsiveContainer width="100%" height={H}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="bucket" tick={AXIS} axisLine={{ stroke: GRID }} tickLine={false}
          tickFormatter={(v) => Number(v).toFixed(1)} />
        <YAxis tick={AXIS} axisLine={{ stroke: GRID }} tickLine={false} width={50} />
        {tip()}
        <Bar dataKey="customers" radius={[2, 2, 0, 0]}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.bucket >= 0.8 ? ALERT : d.bucket >= 0.5 ? AMBER : GREEN} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
```

Note on `segmentName`: the warehouse returns `segment_name` already resolved (e.g. "Champions"), so charts use it directly; `segmentName` import is only needed if mapping ids — remove the import if unused to keep ruff/eslint/tsc clean. Verify `usd` exists in `lib/utils.ts` (it does, per the summary: `usd`, `churnBand`, `fmtDate`). If `usd`'s signature differs, adapt the `tickFormatter`/`formatter` calls.

- [ ] **Step 3: Create the Dashboard page**

Create `app/frontend/src/pages/Dashboard.tsx`:

```tsx
import { ExternalLink } from "lucide-react";

import {
  ChurnDistributionChart,
  SegmentChurnChart,
  SegmentLtvChart,
  TicketsTrendChart,
  TopProductsChart,
} from "@/components/charts";
import { EmptyState, ErrorState, Skeleton } from "@/components/states";
import { Panel, PanelHeader } from "@/components/ui";
import { useConfig, useDashboardAnalytics } from "@/lib/queries";

function ChartPanel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Panel>
      <PanelHeader>
        <span className="font-display text-sm uppercase tracking-[0.14em] text-lum">{title}</span>
      </PanelHeader>
      <div className="p-4">{children}</div>
    </Panel>
  );
}

export default function Dashboard() {
  const cfg = useConfig();
  const { data, isLoading, isError, refetch } = useDashboardAnalytics();

  const workspaceUrl =
    cfg.data?.databricks_host && cfg.data?.dashboard_id
      ? `${cfg.data.databricks_host}/dashboardsv3/${cfg.data.dashboard_id}`
      : null;

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl uppercase tracking-[0.12em] text-lum">
            Fleet Analytics
          </h1>
          <p className="font-mono text-xs text-muted">External feed · AI/BI · warehouse (OBO)</p>
        </div>
        {workspaceUrl && (
          <a
            href={workspaceUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-sm border border-bezel bg-face px-3 py-2 font-display text-xs uppercase tracking-[0.14em] text-lum/80 hover:border-lum/40 hover:text-lum"
          >
            <ExternalLink className="h-3.5 w-3.5" strokeWidth={2} />
            Open in AI/BI workspace
          </a>
        )}
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-80 w-full" />
          ))}
        </div>
      )}

      {isError && (
        <div className="bezel">
          <ErrorState
            message="Analytics feed unavailable. On the deployed app this reads live via your workspace session; locally it needs an OBO token."
            onRetry={() => refetch()}
          />
        </div>
      )}

      {data && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <ChartPanel title="Avg LTV by Segment">
            <SegmentLtvChart data={data.segments} />
          </ChartPanel>
          <ChartPanel title="Avg Churn by Segment">
            <SegmentChurnChart data={data.segments} />
          </ChartPanel>
          <ChartPanel title="Top 15 Products by Revenue">
            {data.products.length ? (
              <TopProductsChart data={data.products} />
            ) : (
              <EmptyState title="No revenue" />
            )}
          </ChartPanel>
          <ChartPanel title="Churn-Risk Distribution">
            <ChurnDistributionChart data={data.churn_buckets} />
          </ChartPanel>
          <div className="lg:col-span-2">
            <ChartPanel title="Weekly Support Tickets by Category">
              <TicketsTrendChart data={data.tickets} />
            </ChartPanel>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Wire the route**

In `app/frontend/src/main.tsx`:
- Add the lazy import alongside the others:
```tsx
const Dashboard = lazy(() => import("./pages/Dashboard"));
```
- Replace the `dashboard` route's element (currently `<ComingSoon title="Dashboard" ... />`) with:
```tsx
      {
        path: "dashboard",
        element: (
          <Suspense fallback={<RouteFallback />}>
            <Dashboard />
          </Suspense>
        ),
      },
```
Leave the `reports` `ComingSoon` route unchanged (that's T7).

- [ ] **Step 5: Typecheck + build**

Run:
```bash
cd app && bunx tsc --noEmit -p tsconfig.json && bun run build
```
Expected: no type errors; production build succeeds. If `ComingSoon` import becomes unused in `main.tsx`, keep it — the `reports` route still uses it (verify; only remove if truly orphaned).

- [ ] **Step 6: Visual verification (manual, deployed or token-injected)**

Start servers (`bun run dev` proxying to uvicorn). Locally the analytics call 401s (no OBO) → the error/caution state shows, which is correct. To see charts locally, inject a token via the browser fetch-patch used previously, or verify on the deployed app after T8. Confirm: 5 themed panels, radio-green bars, amber/alert churn tinting, multi-line ticket trend, the workspace deep-link resolves.

- [ ] **Step 7: Commit**

```bash
git add app/package.json app/frontend/src/components/charts.tsx \
    app/frontend/src/pages/Dashboard.tsx app/frontend/src/main.tsx
git commit -m "feat(t4): native cockpit dashboard with Recharts panels"
```

---

## Self-Review

**Spec coverage:**
- `/api/config` (host + dashboard_id + genie_space_id, TTL-cached) → Task 1. ✓
- `/api/dashboard/analytics` (4 gold aggregates, OBO, `asyncio.gather`, TTL-cached, Pydantic models) → Task 2. ✓
- The exact four dataset SQLs → Task 2 `_Q_*` constants (verbatim, catalog/schema via `_run_sql`). ✓
- Five native charts (Avg LTV, Avg Churn, Top Products, Weekly Tickets, Churn Distribution) → Task 4. ✓
- shadcn/ui charts (Recharts) themed to night-flight → Task 4 `charts.tsx`. ✓
- "Open in AI/BI workspace" deep-link preserving the embed skill → Task 4 Dashboard header. ✓
- staleTime tiers (config 5m, analytics 60s) → Task 3. ✓
- Loading skeletons + amber caution state → Task 4 Dashboard. ✓
- Local-dev caveat (no OBO → caution) documented in error copy → Task 4. ✓
- genie_space_id added for T5 reuse, no other Genie work → Task 1. ✓
- Workspace-side embed allowlist is a T8-deploy-time manual action, not code → out of plan scope by design (noted in spec).

**Placeholder scan:** No TBDs; every code step carries full content. Tests carry real assertions.

**Type consistency:** Backend model field names (`segment_name`, `customers`, `avg_ltv`, `avg_churn`, `product_name`, `category`, `revenue`, `units`, `week`, `tickets`, `bucket`) match the TS interfaces in Task 3 and the chart `dataKey`s in Task 4. `AppConfig` fields match across config.py / dashboard.py / types.ts. `_run_sql` mirrors the proven `_run_stmt` signature minus the param.

**Known adaptation points flagged inline:** module-level vs per-test `live` marker (Task 2 Step 1 corrects this); `usd`/`segmentName` import verification (Task 4 Step 2); `ComingSoon` orphan check (Task 4 Step 5).
