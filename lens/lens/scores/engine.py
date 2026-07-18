"""Score engine: gather mart aggregates -> pure scorers -> append-only score_runs.

`gather_inputs` is the only DB-touching step (DuckDB marts/facts + SQLite for
PII completeness, experiments, predictions, score_runs); every scorer is a
pure function over the plain-dict aggregates it returns. `inputs_hash` =
sha256 of the canonically-serialized inputs, so a score run is reproducible:
same mart data -> same hash -> same value. Phase 2 (CONTRACTS.md V2.4): a
score whose inputs are unavailable maps to None and is skipped; the full CIQ
renormalizes its canon weights over whatever computed.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Customer, CustomerPII, ScoreRun
from . import altitude, autopilot, ciq, flow, gravity, pulse, signal, velocity, vitals, watertight

DEFINITION_VERSION = "v2.0"

_SCORERS = (
    ("gravity", gravity.score),
    ("flow", flow.score),
    ("signal", signal.score),
    ("watertight", watertight.score),
    ("vitals", vitals.score),
    ("velocity", velocity.score),
    ("autopilot", autopilot.score),
    ("pulse", pulse.score),
    ("altitude", altitude.score),  # last: consumes this run's signal value
)


def inputs_hash(obj: object) -> str:
    """Stable sha256 of JSON-serializable inputs (sorted keys, canonical separators)."""
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def compute_all(session: Session, tenant_id: int) -> list[ScoreRun]:
    """Compute the nine Punara scores + full CIQ; persist one append-only
    ScoreRun per computed score; return the persisted rows. A score whose
    inputs are unavailable (mart not built yet -> gather_inputs returns None
    for it) is skipped and CIQ renormalizes over the rest (CONTRACTS.md V2.4)."""
    inputs = gather_inputs(session, tenant_id)
    computed_at = datetime.utcnow()
    runs: list[ScoreRun] = []
    values: dict[str, float] = {}
    for name, scorer in _SCORERS:
        score_inputs = inputs.get(name)
        if score_inputs is None:
            continue
        if name == "altitude":  # ladder rung 1 reads this run's Signal value
            score_inputs["signal_value"] = values.get("signal")
        value, components = scorer(score_inputs)
        values[name] = value
        runs.append(
            ScoreRun(
                tenant_id=tenant_id,
                score=name,
                value=value,
                computed_at=computed_at,
                definition_version=DEFINITION_VERSION,
                inputs_hash=inputs_hash(score_inputs),
                components=components,
            )
        )
    ciq_value, ciq_components = ciq.score(values)
    runs.append(
        ScoreRun(
            tenant_id=tenant_id,
            score="ciq",
            value=ciq_value,
            computed_at=computed_at,
            definition_version=DEFINITION_VERSION,
            inputs_hash=inputs_hash(values),
            components=ciq_components,
        )
    )
    session.add_all(runs)
    session.commit()
    return runs


# --------------------------------------------------------------------- gathering


def _one(con, sql: str, *params):  # noqa: ANN001 - duckdb connection
    row = con.execute(sql, params).fetchone()
    return row[0] if row else None


def _months_back(d: date | datetime, n: int) -> date:
    """First of the month n months before d (marts use first-of-month DATEs)."""
    total = d.year * 12 + d.month - 1 - n
    return date(total // 12, total % 12 + 1, 1)


_FIRSTS = """
WITH firsts AS (
    SELECT customer_id,
           min(placed_at) AS first_at,
           min(CASE WHEN customer_order_index = 2 THEN placed_at END) AS second_at
    FROM fact_orders
    WHERE tenant_id = ? AND customer_id IS NOT NULL AND cancelled_at IS NULL
    GROUP BY customer_id
)
"""


def gather_inputs(session: Session, tenant_id: int) -> dict[str, dict]:
    """Read the DuckDB marts (plus SQLite customer_pii) into the plain-dict
    aggregates each scorer consumes. Requires olap.export_core + marts.build
    to have run for this tenant (nightly pipeline order, CONTRACTS.md sec 5)."""
    from .. import olap  # lazy: analytics agent owns olap.py

    con = olap.get_conn()
    t = tenant_id

    as_of = _one(con, "SELECT max(placed_at) FROM fact_orders WHERE tenant_id = ?", t)
    if as_of is None:  # no orders at all: every score reads worst, honestly
        return {
            "gravity": {
                "repeat_rate_90d": 0.0,
                "median_repurchase_days": None,
                "avg_m3_retention": 0.0,
                "repeat_revenue_share": 0.0,
            },
            "flow": {
                "healthy_stage_share": 0.0,
                "new_to_active_rate": 0.0,
                "slipping_to_dormant_rate": 1.0,
                "reactivation_rate": 0.0,
            },
            "signal": {
                "identity_resolution_rate": 0.0,
                "field_completeness": 0.0,
                "payment_match_rate": 0.0,
                "history_months": 0.0,
            },
            "watertight": {"gross_revenue_paise": 0, "leak_paise": {}},
            # Phase-2 scores: unavailable with no order history; CIQ renormalizes.
            "vitals": None,
            "velocity": None,
            "autopilot": None,
            "pulse": None,
            "altitude": None,
        }

    # ---- gravity
    repeat_rate = (
        _one(
            con,
            _FIRSTS
            + """
            SELECT avg(CASE WHEN second_at IS NOT NULL
                             AND second_at <= first_at + INTERVAL 90 DAY
                        THEN 1.0 ELSE 0.0 END)
            FROM firsts WHERE first_at <= ?
            """,
            t,
            as_of - timedelta(days=90),
        )
        or 0.0
    )
    median_days = _one(
        con,
        _FIRSTS + "SELECT median(date_diff('day', first_at, second_at)) FROM firsts WHERE second_at IS NOT NULL",
        t,
    )
    avg_m3 = (
        _one(con, "SELECT avg(retention_rate) FROM cohort_retention WHERE tenant_id = ? AND months_since = 3", t)
        or 0.0
    )
    kpi_max = _one(con, "SELECT max(month) FROM executive_kpis WHERE tenant_id = ?", t)
    window_start = _months_back(kpi_max, 11) if kpi_max is not None else None
    repeat_rev_share = 0.0
    if window_start is not None:
        repeat_rev_share = (
            _one(
                con,
                """
                SELECT sum(repeat_revenue_paise) * 1.0 / nullif(sum(total_revenue_paise), 0)
                FROM executive_kpis WHERE tenant_id = ? AND month >= ?
                """,
                t,
                window_start,
            )
            or 0.0
        )

    # ---- flow
    healthy_share = (
        _one(
            con,
            """
            SELECT avg(CASE WHEN lifecycle_stage IN ('active', 'loyal') THEN 1.0 ELSE 0.0 END)
            FROM dim_customers WHERE tenant_id = ? AND orders_count > 0
            """,
            t,
        )
        or 0.0
    )
    n2a_rate = (
        _one(
            con,
            """
            SELECT avg(CASE WHEN orders_count >= 2 THEN 1.0 ELSE 0.0 END)
            FROM dim_customers
            WHERE tenant_id = ? AND first_order_at BETWEEN ? AND ?
            """,
            t,
            as_of - timedelta(days=180),
            as_of - timedelta(days=90),
        )
        or 0.0
    )
    rf_max = _one(con, "SELECT max(month) FROM retention_facts WHERE tenant_id = ?", t)
    slip_rate = None
    react_rate = None
    if rf_max is not None:
        month_m3 = _months_back(rf_max, 3)
        transition = """
            SELECT avg(CASE WHEN cur.lifecycle_stage IN {target} THEN 1.0 ELSE 0.0 END)
            FROM retention_facts prev
            JOIN retention_facts cur
              ON cur.tenant_id = prev.tenant_id AND cur.customer_id = prev.customer_id AND cur.month = ?
            WHERE prev.tenant_id = ? AND prev.month = ? AND prev.lifecycle_stage = ?
        """
        slip_rate = _one(
            con, transition.format(target="('dormant', 'lost')"), rf_max, t, month_m3, "slipping"
        )
        react_rate = _one(
            con, transition.format(target="('new', 'active', 'loyal')"), rf_max, t, month_m3, "dormant"
        )

    # ---- signal
    ident_rate = (
        _one(
            con,
            "SELECT avg(CASE WHEN customer_id IS NOT NULL THEN 1.0 ELSE 0.0 END) FROM fact_orders WHERE tenant_id = ?",
            t,
        )
        or 0.0
    )
    total_customers = (
        session.scalar(
            select(func.count())
            .select_from(Customer)
            .where(Customer.tenant_id == t, Customer.merged_into_customer_id.is_(None))
        )
        or 0
    )
    complete_customers = (
        session.scalar(
            select(func.count())
            .select_from(CustomerPII)
            .join(Customer, Customer.id == CustomerPII.customer_id)
            .where(
                Customer.tenant_id == t,
                Customer.merged_into_customer_id.is_(None),
                CustomerPII.primary_phone.is_not(None),
                CustomerPII.primary_email.is_not(None),
            )
        )
        or 0
    )
    field_completeness = complete_customers / total_customers if total_customers else 0.0
    payment_match = (
        _one(
            con,
            """
            SELECT avg(CASE WHEN p.order_id IS NOT NULL THEN 1.0 ELSE 0.0 END)
            FROM fact_orders o
            LEFT JOIN (SELECT DISTINCT tenant_id, order_id FROM fact_payments WHERE status = 'captured') p
              ON p.tenant_id = o.tenant_id AND p.order_id = o.order_id
            WHERE o.tenant_id = ? AND o.cod = false
              AND o.financial_status IN ('paid', 'partially_refunded', 'refunded')
            """,
            t,
        )
        or 0.0
    )
    history_months = (
        _one(
            con,
            "SELECT date_diff('month', min(placed_at), max(placed_at)) + 1 FROM fact_orders WHERE tenant_id = ?",
            t,
        )
        or 0
    )

    # ---- watertight (trailing 12 months, same window as executive_kpis above)
    gross_revenue = 0
    leak_paise: dict[str, int] = {}
    if window_start is not None:
        gross_revenue = int(
            _one(
                con,
                "SELECT sum(total_revenue_paise) FROM executive_kpis WHERE tenant_id = ? AND month >= ?",
                t,
                window_start,
            )
            or 0
        )
        rows = con.execute(
            "SELECT leak_type, sum(amount_paise) FROM leak_facts WHERE tenant_id = ? AND month >= ? GROUP BY leak_type",
            (t, window_start),
        ).fetchall()
        leak_paise = {leak_type: int(amount or 0) for leak_type, amount in rows}

    # ---- Phase-2 scorers: the queries.py assemblers are the pinned seam
    # (CONTRACTS V2.9) — one copy, tested there. A raising assembler (mart not
    # built yet) maps to None: score skipped, CIQ renormalizes (V2.4).
    from .. import queries

    def _maybe(fn, *args):  # noqa: ANN001
        try:
            return fn(*args)
        except Exception as exc:
            print(f"scores: {fn.__name__} unavailable ({exc}); score skipped")
            return None

    return {
        "gravity": {
            "repeat_rate_90d": float(repeat_rate),
            "median_repurchase_days": None if median_days is None else float(median_days),
            "avg_m3_retention": float(avg_m3),
            "repeat_revenue_share": float(repeat_rev_share),
        },
        "flow": {
            "healthy_stage_share": float(healthy_share),
            "new_to_active_rate": float(n2a_rate),
            "slipping_to_dormant_rate": None if slip_rate is None else float(slip_rate),
            "reactivation_rate": None if react_rate is None else float(react_rate),
        },
        "signal": {
            "identity_resolution_rate": float(ident_rate),
            "field_completeness": float(field_completeness),
            "payment_match_rate": float(payment_match),
            "history_months": float(history_months),
        },
        "watertight": {"gross_revenue_paise": gross_revenue, "leak_paise": leak_paise},
        "vitals": _maybe(queries.vitals_inputs, t),
        "velocity": _maybe(queries.velocity_inputs, t),
        "autopilot": _maybe(queries.autopilot_inputs, t),
        "pulse": _maybe(queries.pulse_inputs, t),
        "altitude": _maybe(queries.altitude_inputs, session, t),
    }
