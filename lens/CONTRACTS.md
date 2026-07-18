# Punara Lens v0 — CONTRACTS

This is THE seam document. Parallel builders code against it, not against each
other's branches. If you need to change a seam, change this file first and say
so in your return. Foundation (models, config, db, events, CLI) is already
built — import it, do not rewrite it.

Non-negotiables (repeated from the blueprint because they are load-bearing):

- **Money is integer paise everywhere.** Column and JSON key names end in `_paise`. Never floats, never rupees-with-decimals.
- **Every tenant-scoped table/query carries and filters `tenant_id`.**
- **Idempotent ingestion:** unique `(tenant_id, source, external_id)`; re-running any job is a no-op.
- **Deterministic seeds:** generators use `random.Random(seed)` / `numpy.random.default_rng(seed)` / `Faker.seed(seed)` only. No wall-clock randomness.
- **PII isolation:** names/emails/phones live ONLY in the `customer_pii` table (SQLite). Nothing PII is ever exported to DuckDB or returned by list endpoints; `customer_detail` reads PII from SQLite directly.
- **`event_id` = `sha256(f"{tenant_id}|{source}|{external_id}|{event_name}")`** — use `lens.events.event_id()`.
- **Servers bind 127.0.0.1 only.** API :8010, web :3010. No external network calls at runtime except localhost.
- Python: type-hinted, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Pydantic v2. Timestamps naive UTC `datetime` in storage.
- Config: `from lens.config import settings` — `settings.db_url`, `settings.olap_path`, `settings.api_host`, `settings.api_port`. Sessions: `from lens.db import get_session`.

---

## 1. Module ownership map

| Path | Owner | Contents |
|---|---|---|
| `lens/lens/models.py`, `config.py`, `db.py`, `events.py`, `cli.py` | **foundation (done)** | schema, settings, session factory, event dictionary, CLI |
| `lens/lens/seed.py` | **seeder agent** | synthetic Shopify/Razorpay/Shiprocket/Klaviyo data → `raw_records` + catalog |
| `lens/lens/connectors/` (`base.py`, `shopify.py`, `klaviyo.py`, synthetic transports) | **connector agent** | raw_records → core tables |
| `lens/lens/identity.py` | **connector agent** | deterministic phone-first identity resolution |
| `lens/lens/olap.py`, `lens/lens/marts.py`, `lens/lens/queries.py` | **analytics agent** | core → DuckDB events+dims; mart builds; typed reads |
| `lens/lens/scores/` (`engine.py`, one module per score) | **scores agent** | Gravity, Flow, Signal, Watertight, partial CIQ |
| `lens/lens/api/` (`app.py`, routers) | **api agent** | FastAPI `/v1` REST, thin wrapper over `queries.py` |
| `web/` | **frontend agent** | Next.js dashboard on 127.0.0.1:3010, consumes the REST API |

Do not edit files outside your row. If a seam is missing, add it here first.

## 2. Cross-module seams (exact signatures)

Report types are frozen dataclasses defined in the module that returns them.
All functions are synchronous plain Python (no async outside the API layer).

### 2.1 `lens/lens/seed.py` — seeder agent

```python
@dataclass(frozen=True)
class SeedReport:
    tenant_id: int
    tenant_slug: str
    months: int
    seed: int
    counts: dict[str, int]   # table/resource name -> rows written

def run(session: Session, tenant_slug: str, months: int = 24, seed: int = 42) -> SeedReport: ...
```

Behavior: creates (or reuses, by slug) the `Tenant`; writes 24 months of
realistic synthetic history as **`raw_records` rows** (source-shaped JSON
payloads for `shopify` orders/customers/products, `razorpay` payments,
`shiprocket` shipments, `klaviyo` campaigns/messages/consent) plus `products`/
`variants` catalog rows directly. The connector pipeline turns raw into core —
the seeder does NOT write orders/customers/messages core rows itself.
Idempotent: same (tenant, seed, months) → same external_ids → re-run is a
no-op via the unique constraints. Realism bar: repeat rate ~25-35%, COD share
~40-60%, RTO on COD ~15-25%, failed payments ~3-6% of attempts, monthly
seasonality + growth trend, a discernible discount-abuse tail.

Raw-record vocabulary the seeder writes and connectors read (seeder agent):
`(shopify, customers|products|orders)` · `(razorpay, payments)` ·
`(shiprocket, shipments)` · `(klaviyo, campaigns|messages|consent)`.
Refunds are embedded in the shopify order payload under `"refunds"` (each
with its own `id`, `amount_paise`, `refund_type`, `processed_at`) — there is
no separate refunds resource, mirroring Shopify's order JSON. Money keys in
raw payloads are integer `*_paise` (the repo money convention outranks
Shopify's decimal-string cosplay). Razorpay/Shiprocket payloads reference
their order via `order_external_id`; klaviyo payloads carry a
`profile: {id, email, phone}` block for identity linking. Guest orders have
`customer: null` and are keyed by top-level `phone`/`email`. Klaviyo campaign
payloads use `campaign_type`/`started_at` keys; shiprocket shipments use
`shipped_at`/`delivered_at`/`rto_at` and lowercase statuses; variants are
keyed by `external_id`. (The connector mappers dual-read these seeded keys
AND the public-API spellings — integration note.) The seed anchor
is the fixed constant `seed.HISTORY_END` (2026-07-01) — never wall clock.
`seed.run` also accepts an extra keyword `customers: int = 9000` (universe
scale; tests use small values).

### 2.2 `lens/lens/connectors/` — connector agent

```python
# base.py
@dataclass(frozen=True)
class SyncReport:
    tenant_id: int
    source: str              # "shopify" | "klaviyo"
    resources: dict[str, int]  # resource -> core rows upserted
    started_at: datetime
    finished_at: datetime

class SyncRunner:
    def run(self, session: Session, tenant_id: int, source: str) -> SyncReport: ...
```

`SyncRunner.run` reads unprocessed `raw_records` for (tenant, source) — the
"synthetic transport" is simply raw_records already seeded; the transport
abstraction must keep a seam where a real HTTP client slots in later — and
upserts core rows (`customers`+`customer_pii`+`customer_identities`, `orders`,
`order_items`, `refunds`, `payments`, `shipments`, `campaigns`, `messages`,
`consent_ledger`), keyed on `(tenant_id, source, external_id)`. Updates
`sync_state` cursor per resource. Razorpay/Shiprocket raw records are ingested
under the `shopify` sync run (they attach to orders); Klaviyo handles
campaigns/messages/consent. Maintains denormalized `customers.orders_count /
total_spent_paise / first_order_at / last_order_at / customer_order_index` and
lifecycle_stage (rules: `new` = 1 order <90d; `active` = last order <90d and
2+ orders; `loyal` = 4+ orders and last <120d; `slipping` = last order 90-180d;
`dormant` = 180-365d; `lost` = >365d).

```python
# identity.py
@dataclass(frozen=True)
class ResolveReport:
    tenant_id: int
    customers_before: int
    customers_after: int
    merges: int
    orders_attached: int     # guest orders that gained a customer_id
    unresolved_orders: int   # still customer_id IS NULL

def resolve(session: Session, tenant_id: int) -> ResolveReport: ...
```

Deterministic only. Precedence: (1) `shopify_customer_id`, (2) phone E.164,
(3) email lowercased/trimmed. Survivor = earliest `first_order_at` (else
earliest `created_at`). Merge writes an `identity_edges` row, repoints
`customer_identities`/orders/child FKs, sets `merged_into_customer_id` on the
absorbed row (never delete), recomputes `customer_order_index`. Re-run = no-op.

### 2.3 `lens/lens/olap.py` + `marts.py` + `queries.py` — analytics agent

```python
# olap.py
def get_conn() -> duckdb.DuckDBPyConnection: ...   # opens settings.olap_path
def export_core(session: Session, tenant_id: int) -> None: ...
```

`export_core` replaces (DELETE by tenant_id + INSERT, or CREATE TABLE IF NOT
EXISTS then swap) the DuckDB **events** table rows for that tenant, derived
from core rows per the event dictionary (`lens.events.EVENTS`), plus
pseudonymous dim/fact copies: `dim_customers`, `dim_products`, `dim_variants`,
`fact_orders`, `fact_order_items`, `fact_refunds`, `fact_payments`,
`fact_shipments`, `dim_campaigns`, `fact_messages`, `fact_consent` — column
names/types mirror models.py minus ALL PII (customer_pii is never exported).
Dedup key on events: `event_id`.

```python
# marts.py
def build(tenant_id: int) -> None: ...   # CREATE OR REPLACE each mart for this tenant
```

Rebuilds the six marts (schemas in section 4) from events+dims inside DuckDB.
Rebuild is full-replace per tenant and idempotent.

```python
# queries.py — typed reads the API serves verbatim; each returns JSON-shaped
# dicts/lists (the exact `data` payloads in section 3). SQLite session is only
# needed where noted; everything else reads DuckDB.
def overview_kpis(tenant_id: int) -> dict: ...
def cohort_matrix(tenant_id: int) -> dict: ...
def rfm_grid(tenant_id: int) -> dict: ...
def revenue_monthly(tenant_id: int) -> list[dict]: ...
def leaks_summary(tenant_id: int) -> dict: ...
def customers_page(tenant_id: int, segment: str | None = None, page: int = 1, page_size: int = 50) -> dict: ...
def customer_detail(session: Session, tenant_id: int, customer_id: int) -> dict | None: ...  # joins PII from SQLite
def scores_latest(session: Session, tenant_id: int) -> dict: ...        # reads score_runs (SQLite)
def score_history(session: Session, tenant_id: int, score: str) -> list[dict]: ...
```

### 2.4 `lens/lens/scores/engine.py` — scores agent

```python
def compute_all(session: Session, tenant_id: int) -> list[ScoreRun]: ...
```

Computes **gravity, flow, signal, watertight** (0-100 floats) from the DuckDB
marts via `queries.py`/direct mart SQL, plus **ciq_partial** = weighted mean of
those four with canon weights renormalized (gravity 20, flow 12, signal 12,
watertight 12 → /56). Persists one `lens.models.ScoreRun` row per score
(append-only), `definition_version="v0.1"`, `inputs_hash` = sha256 of the
serialized mart inputs, `components` = named sub-score dict. Returns the
persisted rows. Component definitions (v0 simplifications of
blueprint/05_service_portfolio.md §5; benchmark constants hard-coded in-repo):

- **gravity**: repeat_rate_90d (40) · repurchase_latency (25) · cohort_decay (25) · repeat_revenue_share (10)
- **flow**: stage_distribution (35) · new_to_active_velocity (30) · slipping_to_dormant_leak (25) · reactivation_rate (10)
- **signal**: identity_resolution_rate (35) · field_completeness (25) · cross_source_reconciliation (25) · history_depth (15)
- **watertight**: per-leak sub-score `100 * (1 - min(leak_share, p90)/p90)`, weighted: preventable_churn 40 · rto_cod 30 · failed_payments 15 · discount_abuse 15. Raw paise always reported in components.

The other six scores are NOT computed in v0 — the API reports them as
`"status": "phase_2"`.

### 2.5 `lens/lens/api/` — api agent

FastAPI app at `lens/lens/api/app.py`, exported as `app`. Serves section 3
verbatim by calling `queries.py`. `lens api` CLI runs
`uvicorn lens.api.app:app` on `settings.api_host:settings.api_port`
(127.0.0.1:8010). CORS: allow origin `http://127.0.0.1:3010` and
`http://localhost:3010` only. No auth in v0 (localhost-only). 404 JSON:
`{"detail": "..."}` (FastAPI default).

### 2.6 `web/` — frontend agent

Next.js (App Router, TypeScript, Tailwind), dev server `127.0.0.1:3010`.
Reads `NEXT_PUBLIC_LENS_API` (default `http://127.0.0.1:8010`). Palette/type
per `blueprint/_canon.md` §12 (Nightfall #101623 bg, Bone #FAF7F0, Marigold
#F2A413 accent, Loop Teal #0FA284 positive, Ember #E0533D risk, Graphite
#5A6272 muted; Fraunces headings, Inter body, IBM Plex Mono numbers).
Pages: overview (KPIs + scores), cohorts, RFM, revenue, leaks, customers
(list + detail), score history.

## 3. REST contract — `/v1`

All endpoints `GET`, JSON. Money integer paise. Rates/ratios are 0-1 doubles.
Months are `"YYYY-MM"` strings. Timestamps ISO-8601 UTC (`"2026-07-01T00:00:00Z"`).
Unknown tenant / customer → 404 `{"detail": "tenant not found"}`.
(API addition: error bodies also carry `"error": {"code", "message"}` alongside
`detail` — read whichever you prefer. `{id}` path segments accept the numeric
tenant id or the slug.)

### GET /v1/health

```json
{ "data": { "status": "ok", "db": true, "olap": true } }
```

`status` = `ok|degraded`; `db` = SQLite reachable, `olap` = DuckDB file exists.

### GET /v1/tenants/{id}/meta

Data freshness (stale data is a client-facing fact — 08 §11): last sync per
source from `sync_state`, last score run from `score_runs`. Nulls when never run.

```json
{
  "data": {
    "tenant_id": 1,
    "syncs": [
      { "source": "klaviyo", "last_synced_at": "2026-07-16T02:05:00Z" },
      { "source": "shopify", "last_synced_at": "2026-07-16T02:00:00Z" }
    ],
    "last_score_run_at": "2026-07-16T02:10:00Z",
    "definition_version": "v0.1"
  }
}
```

### GET /v1/tenants

```json
{
  "data": [
    {
      "id": 1,
      "slug": "meadow",
      "name": "Meadow Botanicals",
      "shopify_domain": "meadow-botanicals.myshopify.com",
      "base_currency": "INR",
      "plan": "advisory",
      "status": "active"
    }
  ]
}
```

### GET /v1/tenants/{id}/overview

```json
{
  "data": {
    "as_of": "2026-07-01T00:00:00Z",
    "window_months": 12,
    "total_revenue_paise": 184500000,
    "repeat_revenue_paise": 52100000,
    "repeat_rate": 0.31,
    "orders": 14210,
    "customers": 9840,
    "new_customers_last_month": 412,
    "aov_paise": 129800,
    "leak_total_paise": 9400000,
    "scores": {
      "ciq_partial": 58.4,
      "gravity": 61.2,
      "flow": 54.0,
      "signal": 72.5,
      "watertight": 44.1
    }
  }
}
```

### GET /v1/tenants/{id}/scores

```json
{
  "data": {
    "computed_at": "2026-07-01T02:00:00Z",
    "definition_version": "v0.1",
    "scores": [
      {
        "score": "gravity",
        "value": 61.2,
        "status": "computed",
        "components": {
          "repeat_rate_90d": 55.0,
          "repurchase_latency": 62.1,
          "cohort_decay": 68.0,
          "repeat_revenue_share": 60.4
        }
      },
      {
        "score": "watertight",
        "value": 44.1,
        "status": "computed",
        "components": {
          "preventable_churn": 38.0,
          "rto_cod": 41.5,
          "failed_payments": 71.0,
          "discount_abuse": 55.2,
          "leak_total_paise": 9400000
        }
      },
      { "score": "flow", "value": 54.0, "status": "computed", "components": {} },
      { "score": "signal", "value": 72.5, "status": "computed", "components": {} },
      { "score": "ciq_partial", "value": 58.4, "status": "computed", "components": {} },
      { "score": "vitals", "value": null, "status": "phase_2", "components": {} },
      { "score": "velocity", "value": null, "status": "phase_2", "components": {} },
      { "score": "autopilot", "value": null, "status": "phase_2", "components": {} },
      { "score": "pulse", "value": null, "status": "phase_2", "components": {} },
      { "score": "altitude", "value": null, "status": "phase_2", "components": {} }
    ]
  }
}
```

(`components` abbreviated above only for this document — real responses carry
the full component dict for every computed score. Integration note: alongside
each 0-100 sub-score the engine emits flat `<name>_raw` (the underlying
metric, may be null) and `<name>_note` (string: benchmark + weight) siblings,
and `ciq_partial` components carry `coverage`/`weights_renormalized`/
`phase_2`/`note` extras — clients must tolerate non-numeric component values.)

### GET /v1/tenants/{id}/scores/{name}/history

`name` in `gravity|flow|signal|watertight|ciq_partial`, else 404.

```json
{
  "data": [
    { "computed_at": "2026-06-01T02:00:00Z", "value": 59.8, "definition_version": "v0.1" },
    { "computed_at": "2026-07-01T02:00:00Z", "value": 61.2, "definition_version": "v0.1" }
  ]
}
```

### GET /v1/tenants/{id}/cohorts

```json
{
  "data": {
    "cohorts": [
      {
        "cohort_month": "2025-01",
        "cohort_size": 380,
        "cells": [
          { "months_since": 0, "active_customers": 380, "retention_rate": 1.0, "repeat_revenue_paise": 0 },
          { "months_since": 1, "active_customers": 72, "retention_rate": 0.189, "repeat_revenue_paise": 9210000 },
          { "months_since": 2, "active_customers": 51, "retention_rate": 0.134, "repeat_revenue_paise": 6480000 }
        ]
      }
    ]
  }
}
```

### GET /v1/tenants/{id}/rfm

```json
{
  "data": {
    "as_of": "2026-07-01",
    "segments": [
      {
        "segment": "champions",
        "customers": 512,
        "revenue_paise": 41200000,
        "avg_recency_days": 21,
        "avg_frequency": 6.2,
        "avg_monetary_paise": 80500
      },
      {
        "segment": "at_risk",
        "customers": 1204,
        "revenue_paise": 22100000,
        "avg_recency_days": 148,
        "avg_frequency": 3.1,
        "avg_monetary_paise": 18400
      }
    ],
    "grid": [
      { "r_quintile": 5, "f_quintile": 5, "customers": 210, "revenue_paise": 18900000 },
      { "r_quintile": 5, "f_quintile": 4, "customers": 168, "revenue_paise": 12100000 }
    ]
  }
}
```

RFM segment labels (canonical set, from r/f quintiles): `champions` (r>=4,f>=4),
`loyal` (r>=3,f>=4), `potential_loyalist` (r>=4,f 2-3), `new` (r>=4,f=1),
`promising` (r=3,f<=2), `needs_attention` (r=3,f=3), `about_to_sleep` (r=2,f<=2),
`at_risk` (r<=2,f>=3), `cant_lose` (r=1,f>=4), `hibernating` (r<=2,f<=2 remainder).

### GET /v1/tenants/{id}/revenue

```json
{
  "data": [
    {
      "month": "2026-06",
      "revenue_paise": 15400000,
      "repeat_revenue_paise": 5100000,
      "orders": 1180,
      "new_customers": 402,
      "returning_customers": 231,
      "repeat_rate": 0.331,
      "aov_paise": 130500
    }
  ]
}
```

### GET /v1/tenants/{id}/leaks

```json
{
  "data": {
    "window_months": 12,
    "total_paise": 9400000,
    "annualized_paise": 9400000,
    "revenue_share": 0.051,
    "leaks": [
      { "leak_type": "rto_cod", "amount_paise": 4100000, "orders_affected": 512, "revenue_share": 0.022 },
      { "leak_type": "preventable_churn", "amount_paise": 3200000, "orders_affected": 0, "revenue_share": 0.017 },
      { "leak_type": "failed_payments", "amount_paise": 1300000, "orders_affected": 209, "revenue_share": 0.007 },
      { "leak_type": "discount_abuse", "amount_paise": 800000, "orders_affected": 340, "revenue_share": 0.004 }
    ],
    "monthly": [
      { "month": "2026-06", "leak_type": "rto_cod", "amount_paise": 380000 }
    ]
  }
}
```

`leak_type` vocabulary (fixed): `preventable_churn | rto_cod | failed_payments | discount_abuse`.

### GET /v1/tenants/{id}/campaigns

*(Seam added by the frontend agent: the /revenue page shows a campaign_roi
table; the mart exists (§4.3) but had no REST surface. API agent: serve the
`campaign_roi` mart rows verbatim. The frontend degrades to an empty state on
404 until this lands.)*

```json
{
  "data": [
    {
      "campaign_id": 12,
      "campaign_name": "Diwali Winback",
      "channel": "email",
      "campaign_type": "campaign",
      "sends": 8200,
      "delivered": 8034,
      "unique_opens": 3110,
      "unique_clicks": 512,
      "unsubscribes": 41,
      "bounces": 166,
      "attributed_orders": 188,
      "attributed_revenue_paise": 24400000,
      "revenue_per_message_paise": 2975
    }
  ]
}
```

### GET /v1/tenants/{id}/customers?segment=&page=&page_size=

`segment` filters by RFM label (optional). Defaults `page=1`, `page_size=50` (max 200). Pseudonymous — no PII in lists.

```json
{
  "data": [
    {
      "id": 4211,
      "lifecycle_stage": "active",
      "rfm_segment": "loyal",
      "orders_count": 5,
      "total_spent_paise": 640000,
      "first_order_at": "2025-03-14T10:22:00Z",
      "last_order_at": "2026-06-02T18:40:00Z",
      "recency_days": 29,
      "whatsapp_opted_in": true
    }
  ],
  "page": 1,
  "page_size": 50,
  "total": 9840
}
```

### GET /v1/tenants/{id}/customers/{key}

`key` = internal customer id (int). The only endpoint that returns PII.

```json
{
  "data": {
    "id": 4211,
    "name": "Ananya Iyer",
    "email": "ananya.iyer@example.com",
    "phone": "+919876543210",
    "lifecycle_stage": "active",
    "rfm_segment": "loyal",
    "orders_count": 5,
    "total_spent_paise": 640000,
    "first_order_at": "2025-03-14T10:22:00Z",
    "last_order_at": "2026-06-02T18:40:00Z",
    "consent": { "email": true, "whatsapp": true, "sms": false },
    "identities": [
      { "identity_type": "shopify_customer_id", "identity_value": "7712334221" },
      { "identity_type": "phone", "identity_value": "+919876543210" }
    ],
    "orders": [
      {
        "id": 88123,
        "order_number": "MB-10442",
        "placed_at": "2026-06-02T18:40:00Z",
        "total_paise": 145000,
        "cod": false,
        "financial_status": "paid",
        "fulfillment_status": "delivered"
      }
    ]
  }
}
```

## 4. DuckDB schemas (file: `settings.olap_path`, default `lens/lens_olap.duckdb`)

All tables carry `tenant_id BIGINT NOT NULL` first. Written only by
`olap.export_core` and `marts.build`. `*_paise` columns are `BIGINT`.

### 4.1 events (canonical stream, dedup key event_id)

```sql
events (
  event_id     VARCHAR NOT NULL,   -- sha256 hex, lens.events.event_id()
  tenant_id    BIGINT  NOT NULL,
  event_name   VARCHAR NOT NULL,   -- closed vocabulary: lens.events.EVENTS
  customer_id  BIGINT,             -- resolved customer, NULL allowed
  order_id     BIGINT,
  message_id   BIGINT,
  occurred_at  TIMESTAMP NOT NULL,
  source       VARCHAR NOT NULL,   -- shopify|razorpay|shiprocket|klaviyo
  external_id  VARCHAR NOT NULL,
  amount_paise BIGINT,             -- monetary events only
  properties   JSON                -- the event's required_properties payload
)
```

### 4.2 dims/facts (pseudonymous mirrors of models.py — same column names, minus PII)

`dim_customers(tenant_id, customer_id, lifecycle_stage, first_order_at,
last_order_at, orders_count, total_spent_paise, accepts_email_marketing,
whatsapp_opted_in, sms_opted_in, created_at)` ·
`dim_products(tenant_id, product_id, title, product_type, vendor, status)` ·
`dim_variants(tenant_id, variant_id, product_id, sku, price_paise, cost_paise)` ·
`fact_orders(tenant_id, order_id, customer_id, placed_at, cancelled_at,
fulfilled_at, delivered_at, financial_status, fulfillment_status, cod,
subtotal_paise, discount_paise, shipping_paise, tax_paise, total_paise,
customer_order_index, discount_codes)` ·
`fact_order_items(tenant_id, order_item_id, order_id, product_id, variant_id,
sku, quantity, unit_price_paise, discount_paise, unit_cost_paise)` ·
`fact_refunds(tenant_id, refund_id, order_id, customer_id, amount_paise,
refund_type, processed_at)` ·
`fact_payments(tenant_id, payment_id, order_id, method, status, amount_paise,
failure_reason, occurred_at)` ·
`fact_shipments(tenant_id, shipment_id, order_id, status, rto, shipped_at,
delivered_at, rto_at)` ·
`dim_campaigns(tenant_id, campaign_id, name, campaign_type, channel,
started_at)` ·
`fact_messages(tenant_id, message_id, campaign_id, customer_id, channel,
sent_at, delivered_at, opened_at, clicked_at, bounced_at, unsubscribed_at)` ·
`fact_consent(tenant_id, consent_id, customer_id, channel, action, occurred_at)`

### 4.3 marts (rebuilt by `marts.build`, full replace per tenant)

```sql
rfm_current (            -- grain: customer, current state
  tenant_id BIGINT, customer_id BIGINT,
  recency_days INTEGER, frequency INTEGER, monetary_paise BIGINT,
  r_quintile TINYINT, f_quintile TINYINT, m_quintile TINYINT,
  rfm_segment VARCHAR,   -- labels in section 3 /rfm
  lifecycle_stage VARCHAR, whatsapp_opted_in BOOLEAN, as_of DATE
)

cohort_retention (       -- grain: acquisition cohort x months_since
  tenant_id BIGINT, cohort_month DATE, months_since INTEGER,
  cohort_size INTEGER, active_customers INTEGER, retention_rate DOUBLE,
  repeat_revenue_paise BIGINT, avg_orders_per_active DOUBLE
)

retention_facts (        -- grain: customer x month; workhorse for Gravity/Flow
  tenant_id BIGINT, customer_id BIGINT, month DATE,
  orders_in_month INTEGER, revenue_in_month_paise BIGINT,
  cumulative_orders INTEGER, cumulative_revenue_paise BIGINT,
  lifecycle_stage VARCHAR,      -- snapshot at month end
  days_since_last_order INTEGER, is_active BOOLEAN,
  rto_orders_in_month INTEGER, refund_paise_in_month BIGINT,
  acquisition_month DATE
)

campaign_roi (           -- grain: campaign; attribution = last click <=7d before order
  tenant_id BIGINT, campaign_id BIGINT, campaign_name VARCHAR,
  channel VARCHAR, campaign_type VARCHAR,
  sends INTEGER, delivered INTEGER, unique_opens INTEGER,
  unique_clicks INTEGER, unsubscribes INTEGER, bounces INTEGER,
  attributed_orders INTEGER, attributed_revenue_paise BIGINT,
  revenue_per_message_paise BIGINT
)

executive_kpis (         -- grain: tenant x month
  tenant_id BIGINT, month DATE,
  total_revenue_paise BIGINT, repeat_revenue_paise BIGINT, repeat_rate DOUBLE,
  orders INTEGER, aov_paise BIGINT,
  new_customers INTEGER, returning_customers INTEGER,
  rto_loss_paise BIGINT, failed_payment_loss_paise BIGINT,
  refund_loss_paise BIGINT, discount_paise BIGINT, leak_total_paise BIGINT
)

leak_facts (             -- grain: tenant x month x leak_type
  tenant_id BIGINT, month DATE,
  leak_type VARCHAR,     -- preventable_churn|rto_cod|failed_payments|discount_abuse
  amount_paise BIGINT, orders_affected INTEGER, revenue_share DOUBLE
)
```

Leak definitions (v0): `rto_cod` = total_paise of RTO'd COD orders (shipment
rto=true, order cod=true) net of recovered value; `failed_payments` =
amount_paise of failed payment attempts on orders never subsequently paid;
`discount_abuse` = discount_paise beyond 30% of subtotal, per order, summed;
`preventable_churn` = expected-value gap of `slipping` customers vs their
trailing run-rate (heuristic; components documented in scores repo).

## 5. Nightly pipeline (the `lens nightly --tenant-id N` command, in order)

1. `SyncRunner().run(session, tenant_id, "shopify")` then `"klaviyo"` — raw → core
2. `identity.resolve(session, tenant_id)` — merge + attach guest orders
3. `olap.export_core(session, tenant_id)` — core → DuckDB events + dims
4. `marts.build(tenant_id)` — dims/events → six marts
5. `scores.engine.compute_all(session, tenant_id)` — marts → score_runs (SQLite)

Every step idempotent; running the pipeline twice changes nothing — with one
deliberate exception: `score_runs` is append-only (§2.4), so each nightly adds
one row per score with identical values/inputs_hash. Every other table's row
counts are unchanged on a re-run. The CLI already wires this order — build
your module to slot in, do not reorder.

## 6. Fixture tenant

Canonical demo tenant the seeder creates and everything else demos against:
slug `meadow`, name `Meadow Botanicals`, a synthetic beauty/personal-care
brand, `meadow-botanicals.myshopify.com`, INR, plan `advisory`, seeded with
`months=24, seed=42`. Tests may create their own tenants with other slugs.

---

# Punara Lens PHASE 2 — CONTRACTS v2

Everything above (v1) stays binding and unedited. This section adds the
Phase-2 seams: the five remaining scores + full CIQ, batch ML predictions,
the WhatsApp/CX/experiments data layer, and the API/dashboard surface.
Foundation (schema, events, seed universe, stubs, CLI wiring) is DONE in this
commit — builders fill in the stubs, they do not reshape them.

## V2.0 Foundation facts builders can rely on

- New core tables (models.py, tenant-scoped, created by `lens init-db`):
  `support_tickets`, `reviews`, `nps_responses`, `experiments`, `predictions`.
  `messages.bounced_at` already existed in v0; there is deliberately NO
  separate `failed` flag — a non-null `bounced_at` IS the failure marker for
  every channel (WhatsApp send failure included).
- New events (lens.events.EVENTS, now 21): `ticket_opened`, `ticket_resolved`,
  `review_submitted`, `nps_submitted`, `experiment_concluded`. WhatsApp
  REUSES `message_sent/delivered/opened/clicked/bounced` with
  `properties.channel == "whatsapp"` — a WhatsApp *read* is `message_opened`,
  a *reply or click* is `message_clicked`, a *send failure* is
  `message_bounced`. One funnel vocabulary across channels; every messaging
  mart stays channel-generic.
- `experiments` is a v2 flattening of 11_data_model.md's
  experiments/variants/results: one row per experiment, readout inline
  (`lift_pct`, `significant`, `decision`). Variant/exposure grain arrives when
  Lens actually assigns treatments — not Phase 2.
- `predictions` upsert key is `(tenant_id, customer_id, model_version,
  scored_on)` where `scored_on = date(scored_at)`: a same-day nightly re-run
  REPLACES that day's rows; a new day APPENDS. Append-only across days keeps
  model drift measurable (11_data_model.md) without letting same-day re-runs
  double rows.
- `nps_responses` are seeded DIRECT to core (no source system exists for a
  Lens-run survey). At seed time core customers don't exist yet, so rows carry
  pseudonymous `customer_external_id` (the shopify external id) and NULL
  `customer_id`; **`seed.link_direct(session, tenant_id)`** fills
  `customer_id` in the nightly after `identity.resolve` (follows merge
  pointers, idempotent). `experiments` are also seeded direct to core, keyed
  `(tenant_id, name)`.
- Seed determinism: all Phase-2 draws come from a SEPARATE stream
  `numpy.random.default_rng([seed, 2])` consumed in fixed order (flows → wa
  campaigns → wa messages → tickets → reviews → nps). The v0 stream is
  untouched, so v0 raw records are byte-identical and v0 score values do not
  shift.

## V2.1 Raw-record vocabulary additions (seeder writes, connectors read)

`(interakt, campaigns|messages|consent)` · `(gorgias, tickets)` ·
`(judgeme, reviews)`. Klaviyo additionally now carries lifecycle FLOWS:
three `campaign_type="flow"` campaigns (`KLF-01` Welcome Series, `KLF-02`
Post-Purchase Care, `KLF-03` 90-Day Winback) plus their triggered messages
(`KLFM-*` external ids) — they sync through the existing klaviyo connector
unchanged. `campaign_type` (`campaign|flow`) is the Autopilot discriminator
between automations and manual blasts.

Payload key spellings (seeded shapes; mappers may also dual-read public-API
spellings, as in v1):

- `interakt/campaigns`: `id, name, campaign_type, channel="whatsapp", started_at`
- `interakt/messages`: `id, campaign_id, profile {id, phone, email},
  channel="whatsapp", sent_at, delivered_at, read_at, clicked_at, failed_at`.
  Mapper mapping into `messages`: `read_at → opened_at`, `clicked_at`
  (reply/click) `→ clicked_at`, `failed_at → bounced_at`.
- `interakt/consent`: `id, profile, channel="whatsapp", action
  (granted|revoked), method (whatsapp_optin|stop_reply), occurred_at`.
- `gorgias/tickets`: `id, order_external_id, customer {external_id} | null,
  email, phone, channel, subject, category
  (delivery_delay|damaged|refund_where|quality|other), status
  (open|pending|resolved|closed), opened_at, first_response_at, resolved_at,
  csat (1-5|null)`.
- `judgeme/reviews`: `id, order_external_id, product_external_id, reviewer
  {external_id|null, email, phone}, rating (1-5), title, body|null, verified,
  submitted_at`.

Seeded realism bars: WhatsApp 1-2 campaigns/week over the full history,
funnel ≈ 95% delivered / 65% read / 8% replied+clicked, conversation-
attributed orders via click-backdating (same mechanism as klaviyo); tickets
on ~6-7% of orders (RTO orders far likelier), resolution log-normal (median
~14h, ~15% breach 72h), CSAT on ~40% of resolved; reviews on ~8% of delivered
orders, mean ≈ 4.1 with RTO/ticket customers skewing low, ~90% verified;
NPS from ~5% of purchasers, promoter-leaning with a detractor cluster among
RTO/ticket-affected customers; 14 experiments over the last 10 months
(9 concluded: 5 shipped / 3 killed / 1 inconclusive; 3 running; 2 draft)
targeting gravity/flow/watertight; email bounces ~2.5% of klaviyo sends
(already in v0).

## V2.2 Connector ownership (Phase-2 builders)

| Path | Owner | Contents |
|---|---|---|
| `lens/lens/connectors/interakt.py` | whatsapp builder | interakt raw → `campaigns`/`messages`/`consent_ledger` core rows |
| `lens/lens/connectors/gorgias.py` | cx builder | gorgias raw → `support_tickets` |
| `lens/lens/connectors/judgeme.py` | cx builder | judgeme raw → `reviews` |
| `lens/lens/ml/engine.py` (+ helpers in `lens/lens/ml/`) | ml builder | predictions pipeline |
| `lens/lens/scores/{vitals,velocity,autopilot,pulse,altitude}.py` + `ciq.py`/`engine.py` v2 changes | scores builder | five scorers + full CIQ |
| `lens/lens/olap.py` / `marts.py` / `queries.py` v2 additions | analytics builder | new exports, four new marts, new typed reads |
| `lens/lens/api/` v2 additions | api builder | predictions/experiments/cx/messaging endpoints, scores v2 |
| `web/` v2 additions | frontend builder | nine tiles + CIQ, Predictions page, WhatsApp/CX tiles |

Stubs exist for all of these (they `raise NotImplementedError`), and
`SyncRunner`/CLI already route the three new sources through
`synthetic.TRANSPORTS` — implement `upsert()` per module docstring; do NOT
change `RESOURCES`/`RESOURCE_SOURCE`/`external_id`. Linking rules: identity
precedence exactly as klaviyo (`shopify external_id > phone > email >
<source>_profile_id`), orders/products via `(tenant, source='shopify',
external_id)`. Ticket/review/nps/experiment writers key on
`(tenant_id, source, external_id)` (experiments: `(tenant_id, name)`).

## V2.3 ML seam — `lens/lens/ml/engine.py`

```python
MODEL_VERSION = "v2.0"

@dataclass(frozen=True)
class MlReport:
    tenant_id: int
    model_version: str
    customers_scored: int
    band_counts: dict[str, int]   # churn_band -> customers

def run(session: Session, tenant_id: int) -> MlReport: ...
```

Nightly batch per 08_technical_architecture.md §7: BG/NBD fits
(frequency, recency, T) per customer from `fact_orders` (DuckDB), giving
`p_alive` and `expected_orders_90d`; Gamma-Gamma on repeat purchasers gives
expected monetary value → `ltv_12m_paise = round(expected_orders_12m *
expected_order_value)` in integer paise. Churn bands from p_alive:
`high < 0.35 <= medium < 0.65 <= low`. Writes `lens.models.Prediction` rows
with the V2.0 upsert semantics; `scored_at` is run wall-clock (run metadata,
like `score_runs.computed_at`), all model INPUTS are data-anchored — no
wall-clock features.

**Stack decision (final):** BG/NBD + Gamma-Gamma implemented in-repo, fit via
`scipy.optimize` — the `lifetimes` package is unmaintained and pins old
numpy/pandas. Churn banding is threshold-on-p_alive for v2;
`sklearn.ensemble.HistGradientBoostingClassifier` is the named upgrade path
if feature-based bands are wanted — **xgboost is rejected** (native-DLL
friction on Windows for zero v2 gain). `scipy` + `scikit-learn` are already
in pyproject.toml. Determinism: fixed `random_state`/seeds only. Customers
with a single order get the population prior (documented in components), not
NaNs. Predictions stay in SQLite; `queries.py` reads them directly (same
pattern as `score_runs`) — they are NOT exported to DuckDB in v2.

## V2.4 Scores — five new scorers + full CIQ

Each scorer is a pure function, v0 style, in its own module:

```python
def score(inputs: dict) -> tuple[float, dict]:   # (0-100, components)
```

`scores/engine.py` (scores builder) extends `_SCORERS` with the five names,
extends `gather_inputs` with the input-assembly queries below (DuckDB marts +
SQLite where noted), and stamps `definition_version = "v2.0"` on all Phase-2
runs. Components keep the v1 conventions: 0-100 sub-scores weighted per
05_service_portfolio.md §5.3, plus `<name>_raw` / `<name>_note` siblings;
benchmark constants hard-coded in-repo.

- **vitals** (Vitals — CRM health): `deliverability` (30, email bounce +
  unsubscribe rates from `messaging_facts` channel='email', trailing 6mo) ·
  `whatsapp_optin` (25, opt-in share of customers from `dim_customers.
  whatsapp_opted_in` + WA failed-send rate from `messaging_facts`
  channel='whatsapp') · `list_hygiene_consent` (25, share of contactable
  customers whose flag is backed by a `fact_consent` grant, and zero
  sends-after-revoke: `fact_messages` × `fact_consent` audit) ·
  `flow_integrity` (20, each of the three seeded flows has sends within the
  last 60 days of history: `dim_campaigns` campaign_type='flow' ×
  `fact_messages`).
- **velocity** (Velocity — experimentation): `cadence` (35, concluded+running
  experiments per month over trailing 6mo vs 2/mo commitment;
  `experiment_facts`) · `validity` (35, share of concluded with
  `significant IS NOT NULL` and `sample_size >= 1000`) · `follow_through`
  (30, share of concluded whose decision is shipped/killed — inconclusive and
  undecided count against).
- **autopilot** (Autopilot — automation coverage): `moment_coverage` (50,
  covered share of the six canonical v2 moments: welcome, post_purchase,
  winback, replenishment, cod_confirmation, abandoned_checkout — from
  `automation_facts.covered`; the seed covers exactly three, by design) ·
  `automated_revenue_share` (30, flow-attributed revenue / all
  message-attributed revenue, `automation_facts`) · `flow_performance` (20,
  flow revenue-per-message vs campaign revenue-per-message,
  `messaging_facts` × `campaign_roi`).
- **pulse** (Pulse — post-purchase CX): `delivery_speed` (30, median
  ship→deliver days vs 5-day benchmark, `cx_facts`) · `rto_ndr` (30, RTO rate
  vs category benchmark, `cx_facts`) · `support` (20, median resolution hours,
  72h breach rate, avg CSAT, `cx_facts`) · `reviews_nps` (20, avg review
  rating trend + NPS, `cx_facts`).
- **altitude** (Altitude — customer maturity): derived proxy of the Decode
  structured assessment (the real thing is a consultant questionnaire; the
  synthetic universe derives it from system usage): `maturity_position` (40,
  ladder: predictions table populated → predictive; marts+scores fresh →
  reporting; else reactive) · `decision_hygiene` (30, share of concluded
  experiments with hypothesis + decision — decision-log proxy) ·
  `capability` (20, sustained experiment cadence + flow upkeep) ·
  `executive_engagement` (10, monthly `score_runs` recompute streak, SQLite).

**Full CIQ** (`scores/ciq.py`): canon v1 weights — Gravity 20 · Flow 12 ·
Signal 12 · Watertight 12 · Vitals 10 · Velocity 10 · Pulse 10 · Autopilot 8 ·
Altitude 6 (sums to 100). Score name in `score_runs` becomes **`ciq`** with
`components.coverage = "9/9"`. Partial mode stays: if any component score is
unavailable (raises/insufficient data), CIQ renormalizes over the available
weights, reports `coverage = "k/9"` and lists the missing names — same
mechanism as v0's `ciq_partial`. Existing `ciq_partial` history rows remain
readable; the engine stops writing new `ciq_partial` rows once `ciq` lands.

## V2.5 New DuckDB marts (analytics builder; full-replace per tenant, like v1)

`olap.export_core` additionally exports (pseudonymous, free text NEVER
exported — review title/body and NPS comments stay in SQLite):
`fact_tickets(tenant_id, ticket_id, customer_id, order_id, channel, category,
status, opened_at, first_response_at, resolved_at, csat)` ·
`fact_reviews(tenant_id, review_id, customer_id, order_id, product_id,
rating, verified, submitted_at)` ·
`fact_nps(tenant_id, nps_id, customer_id, score, channel, responded_at)` ·
`fact_experiments(tenant_id, experiment_id, name, score_target, status,
started_at, concluded_at, sample_size, lift_pct, significant, decision)` —
plus the new voice/experiment events into `events` (nps/experiment rows are
SQLite-sourced; source `punara`).

```sql
cx_facts (                -- grain: tenant x month
  tenant_id BIGINT, month DATE,
  orders_delivered INTEGER, median_delivery_days DOUBLE,
  rto_orders INTEGER, rto_rate DOUBLE,
  tickets_opened INTEGER, ticket_rate DOUBLE,          -- tickets / orders
  median_resolution_hours DOUBLE, breach_rate DOUBLE,  -- resolved > 72h share
  avg_csat DOUBLE,
  reviews INTEGER, avg_review_rating DOUBLE,
  nps_responses INTEGER, nps DOUBLE                    -- %promoters - %detractors, -100..100
)

messaging_facts (         -- grain: tenant x month x channel (email|sms|whatsapp)
  tenant_id BIGINT, month DATE, channel VARCHAR,
  sends INTEGER, delivered INTEGER,
  opened_or_read INTEGER, clicked INTEGER,             -- email opens / whatsapp reads
  bounced INTEGER, bounce_rate DOUBLE, unsubscribed INTEGER,
  attributed_orders INTEGER, attributed_revenue_paise BIGINT,
  revenue_per_message_paise BIGINT   -- whatsapp: this IS revenue-per-conversation (Bet 6)
)

automation_facts (        -- grain: tenant x lifecycle moment
  tenant_id BIGINT,
  moment VARCHAR,          -- welcome|post_purchase|winback|replenishment|cod_confirmation|abandoned_checkout
  covered BOOLEAN, campaign_id BIGINT,                 -- covering flow, NULL if uncovered
  sends INTEGER, attributed_orders INTEGER, attributed_revenue_paise BIGINT,
  automated_revenue_share DOUBLE                       -- of ALL message-attributed revenue
)

experiment_facts (        -- grain: experiment (mirror + derived cadence fields)
  tenant_id BIGINT, experiment_id BIGINT, name VARCHAR, score_target VARCHAR,
  status VARCHAR, decision VARCHAR,
  started_at TIMESTAMP, concluded_at TIMESTAMP, started_month DATE,
  sample_size INTEGER, lift_pct DOUBLE, significant BOOLEAN,
  days_to_decision INTEGER                             -- concluded_at - started_at
)
```

Monthly experiment cadence is DERIVED (GROUP BY started_month over
`experiment_facts`) by the Velocity input query — no second mart. Attribution
rule everywhere: v1's last-click ≤7d before the order, per channel; flow vs
campaign attribution splits on `dim_campaigns.campaign_type`. Moment→flow
mapping for `automation_facts`: campaign external ids `KLF-01/02/03` map to
welcome/post_purchase/winback; the other three moments are uncovered in the
seed (Autopilot must NOT read 100).

## V2.6 Nightly order (wired in cli.py — already done)

1. `SyncRunner().run(...)` for `shopify, klaviyo, interakt, gorgias, judgeme`
   (stubbed sources print a skip notice until their builder lands)
2. `identity.resolve(session, tenant_id)`
3. `seed.link_direct(session, tenant_id)` — attach direct-to-core NPS rows
4. `olap.export_core(session, tenant_id)`
5. `marts.build(tenant_id)`
6. `ml.engine.run(session, tenant_id)` (skip notice while stubbed)
7. `scores.engine.compute_all(session, tenant_id)`

Idempotency contract unchanged: re-running changes nothing except append-only
`score_runs` (and same-day `predictions` upserts replace in place).

## V2.7 REST additions — `/v1` (api builder)

### GET /v1/tenants/{id}/scores — CHANGED

All nine scores return `"status": "computed"` with full components; the
composite row is `"score": "ciq"` (`ciq_partial` disappears from the current
payload once full CIQ lands; its history stays queryable). The overview
`scores` object likewise carries all nine + `ciq`.
`/scores/{name}/history` accepts
`gravity|flow|signal|watertight|vitals|velocity|autopilot|pulse|altitude|ciq|ciq_partial`.

### GET /v1/tenants/{id}/predictions?page=&page_size=

Summary + top-risk page (band `high`, ordered by `ltv_12m_paise` DESC —
rupees at risk first). Reads SQLite `predictions` (latest `scored_on` per
model_version) + `rfm_current` for segment labels. 404 detail
`"no predictions yet"` before the first ml run.

```json
{
  "data": {
    "model_version": "v2.0",
    "scored_at": "2026-07-17T02:10:00Z",
    "customers_scored": 9000,
    "band_counts": { "high": 812, "medium": 2404, "low": 5784 },
    "expected_orders_90d_total": 1240.5,
    "ltv_12m_deciles_paise": [0, 9500, 21000, 36000, 54000, 78000, 108000, 152000, 231000, 480000],
    "at_risk_ltv_paise": 61200000,
    "top_risk": [
      {
        "customer_id": 4211, "p_alive": 0.12, "expected_orders_90d": 0.08,
        "ltv_12m_paise": 84000, "churn_band": "high",
        "rfm_segment": "cant_lose", "lifecycle_stage": "dormant",
        "orders_count": 6, "total_spent_paise": 812000
      }
    ],
    "page": 1, "page_size": 50, "total": 812
  }
}
```

### GET /v1/tenants/{id}/customers/{key} — customer_detail gains

```json
"prediction": {
  "p_alive": 0.84, "expected_orders_90d": 0.61, "ltv_12m_paise": 231000,
  "churn_band": "low", "model_version": "v2.0", "scored_at": "2026-07-17T02:10:00Z"
}
```

(`null` before the first ml run.)

### GET /v1/tenants/{id}/experiments

`experiments` table rows verbatim, newest `started_at` first (drafts last):

```json
{
  "data": [
    {
      "id": 3, "name": "COD-to-prepaid nudge at checkout",
      "hypothesis": "A Rs.50 prepaid incentive cuts COD share 8pts and RTO loss 12%.",
      "score_target": "watertight", "status": "concluded",
      "started_at": "2025-11-03T00:00:00Z", "concluded_at": "2025-12-03T00:00:00Z",
      "sample_size": 6300, "lift_pct": 15.0, "significant": true, "decision": "shipped"
    }
  ]
}
```

### GET /v1/tenants/{id}/cx and GET /v1/tenants/{id}/messaging

Thin mart dumps for the dashboard CX/WhatsApp tiles: `cx` serves `cx_facts`
rows (monthly, ascending); `messaging` serves `messaging_facts` rows plus a
`whatsapp_summary` object (`sends, read_rate, reply_rate,
attributed_revenue_paise, revenue_per_conversation_paise` over the trailing
12 months). Money integer paise; rates 0-1 doubles.

## V2.8 Dashboard additions (frontend builder)

- Overview: all-nine score tiles + the full CIQ hero number (bands 0-40
  Leaking / 40-70 Building / 70-100 Compounding, canon colors).
- `/predictions` page: band counts, LTV decile distribution, top-risk table
  (from V2.7 predictions endpoint).
- Customer detail: prediction block (p_alive, expected 90d orders, 12m LTV,
  band).
- Revenue/overview tiles: WhatsApp revenue-per-conversation + CX tiles
  (median delivery days, RTO rate, median resolution hours, NPS) from
  `/cx` + `/messaging`.
- New score detail pages reuse the existing `scores/[name]` route — names now
  include the five new scores and `ciq`.

## V2.9 Analytics layer — LANDED (analytics builder); seams for api/scores builders

- `dim_campaigns` gained an `external_id VARCHAR` column (V2.5's KLF moment
  mapping needs it; not PII). `olap.get_conn()` migrates pre-v2 files via
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` — no manual step.
- Mart semantics pinned (documented in `marts.py`): messaging attribution is
  per (order, channel) last click ≤7d, revenue in the ORDER's placed month;
  `revenue_per_message_paise = attributed_revenue // delivered` on every
  channel (a bounced send never opened a conversation — for whatsapp this is
  revenue-per-conversation); cx `rto_rate` = rto orders / (delivered + rto)
  that month, `breach_rate` over tickets resolved in the month;
  `automation_facts.automated_revenue_share` is PER ROW (moment revenue /
  ALL message-attributed revenue) — sum covered rows for the tenant share;
  automation rows reuse `campaign_roi`'s single-winner attribution. Canonical
  moment list is `marts.MOMENTS`.
- New typed reads in `queries.py` (api builder serves these verbatim):
  `cx_summary(tenant_id) -> list[dict]` (cx_facts rows, month asc) ·
  `messaging_summary(tenant_id) -> dict` (`{"months": [...], "whatsapp_summary":
  {...}}` per V2.7) · `automation_summary(tenant_id) -> list[dict]` ·
  `experiments_list(session, tenant_id) -> list[dict]` (newest first, drafts
  last) · `experiment_cadence(tenant_id) -> list[dict]` ·
  `predictions_summary(session, tenant_id, page=1, page_size=50) -> dict | None`
  (None before first ml run → 404) · `customer_prediction(session, tenant_id,
  customer_id) -> dict | None` (customer_detail's `prediction` block).
- Scorer-input assemblers in `queries.py` for `scores/engine.gather_inputs`
  (scores builder): `vitals_inputs(t)`, `velocity_inputs(t)`,
  `autopilot_inputs(t)`, `pulse_inputs(t)` (DuckDB) and
  `altitude_inputs(session, t)` (SQLite + DuckDB). All return JSON-serializable
  plain dicts (inputs_hash-safe); windows anchor on mart data clocks, never
  wall clock. Key names are documented by the functions themselves.

## V2.10 Integration reconciliation — LANDED (integration engineer)

The api-builder seams of V2.7 did not exist when the other Phase-2 modules
landed; they were wired at integration time. What is now pinned:

- **V2.7 endpoints live** in `lens/lens/api/analytics.py`:
  `/predictions` (404 `"no predictions yet"` before the first ml run, `page`/
  `page_size` 1..200), `/experiments`, `/cx`, `/messaging`. Payloads are the
  exact dicts from `queries.predictions_summary/experiments_list/cx_summary/
  messaging_summary` served through plain-dict envelopes — the shapes are
  pinned and tested in the queries layer, not re-mirrored as Pydantic models.
- **/messaging row key is `months`** (`{"months": [...], "whatsapp_summary":
  {...}}`) — resolves the spelling the frontend flagged as unpinned.
- **/scores payload**: the nine scores always appear; a missing v0 score is
  `"status": "pending"`, a missing Phase-2 score is `"status": "phase_2"`.
  The composite row is `ciq` whenever a `ciq` run exists (or nothing ran yet)
  and `ciq_partial` only for pre-v2 DBs that never got a full ciq row. The
  overview `scores` object carries the same nine + composite keys.
  `/scores/{name}/history` accepts the full V2.7 name list.
- **customer_detail additions** (now pinned): `prediction` (V2.7 block, null
  before the first ml run) plus `tickets` (id, subject, category, status,
  opened_at, resolved_at, csat), `reviews` (id, rating, title, verified,
  submitted_at), `nps` (id, score, responded_at) — newest first, SQLite-only
  reads (free text never enters DuckDB; this endpoint already serves PII).
- **Test reconciliation**: `test_api.py` vitals-history-404 and
  `test_marts.py` five-key overview assertions contradicted V2.7 and were
  updated; four endpoint smoke tests added to `test_api.py`.
- **Nightly idempotency note**: score VALUES are reproducible except
  `altitude` (and hence `ciq` by ≤0.1), which reads the append-only
  `score_runs` streak (executive_engagement) and predictions freshness by
  design — row counts follow the V2.6 contract exactly.
