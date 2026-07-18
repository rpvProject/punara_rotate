# Punara Lens v0

Internal customer-intelligence platform of **Punara** — retention consultancy
+ SaaS. Local-only: SQLite + DuckDB, servers on 127.0.0.1, no cloud, no
telemetry. Spec lives in `blueprint/`; architecture deviation in
`docs/ADR-001-v0-storage.md`; module seams in `lens/CONTRACTS.md`.

## Quickstart (full version: `lens/README.md`)

```powershell
cd lens
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"

.venv\Scripts\python -m lens init-db
.venv\Scripts\python -m lens seed --tenant meadow --months 24 --seed 42
.venv\Scripts\python -m lens nightly --tenant-id 1
.venv\Scripts\python -m lens api        # http://127.0.0.1:8010/v1/tenants

cd ..\web
npm install
npm run dev                             # http://127.0.0.1:3010
```

## Layout

- `lens/` — Python package: models, connectors, identity, OLAP, marts, scores, API, CLI
- `web/` — Next.js dashboard
- `blueprint/` — the company spec (canon)
- `docs/` — ADRs
- `docker-compose.yml` — FUTURE canonical stack (unused in v0)

## v0 scope

Synthetic seed data (24-month order history) → Shopify/Klaviyo connector
pipeline → phone-first identity resolution → canonical events → RFM, cohort
retention, revenue analytics, leak quantification → four Punara scores
(Gravity, Flow, Signal, Watertight) + partial CIQ → REST `/v1` → dashboard.
LTV/churn ML, Veda, WhatsApp connectors: Phase 2.
