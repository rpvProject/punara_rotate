# ADR-001: v0 storage — SQLite + DuckDB instead of Postgres + ClickHouse

**Status:** accepted (v0 only) · **Date:** 2026-07-17

## Context

Canon (`blueprint/_canon.md` §11, `blueprint/08_technical_architecture.md`)
commits to Postgres 16 (OLTP), ClickHouse (OLAP), and Redis+RQ (jobs), run
locally via docker compose. The v0 build machine is Windows 11 with **no
Docker, no Postgres, no Redis, no make** — Python 3.12 and Node 24 only.

## Decision

- **OLTP core:** SQLite (`lens/lens.db`) via SQLAlchemy 2.0. Transactions,
  FKs, and unique constraints — everything identity resolution and idempotent
  upserts need at v0 scale (1 synthetic tenant, ~10⁵ rows).
- **OLAP/marts:** DuckDB (`lens/lens_olap.duckdb`). Columnar scans for
  cohort/RFM/leak aggregations; same "if the pipeline scans it, it lives in
  the OLAP file" rule as the canon architecture.
- **Jobs:** plain Python functions run by the `lens` CLI; the nightly pipeline
  is one command (`lens nightly`). No queue — nothing in v0 is concurrent.
- Both files are pure `pip install`; zero system installs.

## The swap path (why this is not a rewrite)

- All storage access goes through `lens.config.Settings`:
  `LENS_DB_URL` (SQLAlchemy DSN) and `LENS_OLAP_PATH`. Postgres is a DSN
  change (`postgresql+psycopg://...`); models are already SQLAlchemy 2.0 and
  Postgres-clean (no SQLite-only types).
- The OLAP layer is isolated behind `lens/lens/olap.py` (`get_conn`,
  `export_core`) and `marts.py`; ClickHouse replaces DuckDB behind that seam.
  Mart schemas (CONTRACTS.md §4) already follow ClickHouse conventions:
  tenant-leading keys, denormalized wide tables, integer paise.
- RQ/Redis slot in where the CLI functions are today — each pipeline step is
  already a plain function with (session, tenant_id) signature, i.e. an
  enqueueable job.
- The repo ships the future `docker-compose.yml` (postgres:16, clickhouse,
  redis, all 127.0.0.1-bound) **unused**, so the canon stack is one
  `docker compose up` + two env vars away when Docker exists.

## Consequences

- No Postgres RLS in v0 — tenant isolation is the `tenant_id`-filter
  convention (every query filters by it; enforced in review). RLS returns
  with Postgres.
- SQLite single-writer is fine: one CLI process, one API process (read-mostly).
- DuckDB file locking means `marts.build` and the API share one connection
  path (`olap.get_conn`); acceptable at v0 concurrency.
