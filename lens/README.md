# Punara Lens (v0 + Phase 2)

Local-only customer-intelligence platform: synthetic Shopify/Razorpay/
Shiprocket/Klaviyo/Interakt/Gorgias/Judge.me universe → connector pipeline →
phone-first identity resolution → canonical events (DuckDB) → RFM / cohorts /
revenue / leaks / CX / messaging / automation / experiment marts → batch ML
(BG/NBD + Gamma-Gamma p_alive, expected 90-day orders, 12-month LTV, churn
bands) → all nine Punara scores (Gravity, Flow, Signal, Watertight, Vitals,
Velocity, Autopilot, Pulse, Altitude) + the full CIQ composite (canon weights
20/12/12/12/10/10/10/8/6) → FastAPI `/v1` → Next.js dashboard.

Storage is SQLite (`lens.db`, transactional core) + DuckDB
(`lens_olap.duckdb`, analytics) — see
[docs/ADR-001-v0-storage.md](../docs/ADR-001-v0-storage.md) for why and for
the Postgres/ClickHouse swap path. Module seams live in
[CONTRACTS.md](CONTRACTS.md).

## Quickstart (Windows, from this `lens/` directory)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1              # or call .venv\Scripts\python.exe directly
.venv\Scripts\python.exe -m pip install -e ".[dev]"

.venv\Scripts\python.exe -m lens init-db                 # tables + event dictionary
.venv\Scripts\python.exe -m lens seed                    # 24-month demo universe (tenant "meadow", seed 42)
.venv\Scripts\python.exe -m lens nightly --tenant-id 1   # sync -> identity -> export -> marts -> ml -> scores
.venv\Scripts\python.exe -m lens api                     # REST API on http://127.0.0.1:8010
```

Individual pipeline steps also run standalone: `lens sync`, `lens identity`,
`lens ml` (batch predictions only), `lens scores` — all take `--tenant-id`.

Dashboard (second terminal):

```powershell
cd web
npm install
npm run dev        # pinned to 127.0.0.1:3010 in package.json
```

Every step is idempotent — re-running `seed` or `nightly` is a no-op (the
only growth is `score_runs`, which is append-only by design: reproducibility
is the brand promise; `predictions` upsert per day — a same-day re-run
replaces, a new day appends). `lens seed --tenant <slug> --months N --seed N`
seeds other universes.

## Dashboard pages

`/` (overview: nine score tiles grouped by the Compounding Loop, CIQ dial,
CX/WhatsApp tiles) · `/cohorts` · `/segments` · `/revenue` (channel rollup +
revenue-per-conversation) · `/leaks` · `/customers` (+ detail with prediction
block and order/ticket/review/NPS timeline) · `/predictions` (churn bands,
LTV deciles, top-risk table) · `/experiments` (Loop Ledger) ·
`/scores/[name]` (all nine + `ciq`).

## Port map

| What | Where |
|---|---|
| FastAPI `/v1` REST | `http://127.0.0.1:8010` |
| Next.js dashboard | `http://127.0.0.1:3010` |

**Local-only rule:** both servers bind `127.0.0.1` and nothing else. No cloud
credentials, no telemetry, no external network calls at runtime — the HTTP
transports for live Shopify/Klaviyo/Interakt/Gorgias/Judge.me exist as unused
(untested-against-live) seams.

## ML dependencies

Phase 2 adds `scipy` (BG/NBD + Gamma-Gamma fit in-repo via `scipy.optimize`)
and `scikit-learn` (churn classifier: `HistGradientBoostingClassifier`).
`lifetimes` (unmaintained) and `xgboost` (native-DLL friction on Windows) were
rejected — see [docs/ADR-002-ml-stack.md](../docs/ADR-002-ml-stack.md) and
CONTRACTS.md V2.3.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest tests -q
```

## Conventions (load-bearing)

- Money is **integer paise** everywhere (`*_paise` keys/columns; never floats).
- Every tenant-scoped table/query carries and filters `tenant_id`.
- Idempotent ingestion: unique `(tenant_id, source, external_id)`.
- Deterministic seeds: fixed RNG seed + fixed `HISTORY_END` anchor, no wall clock.
- PII lives only in SQLite `customer_pii`; DuckDB and list endpoints are
  pseudonymous. `GET /v1/tenants/{id}/customers/{key}` is the only PII read.
