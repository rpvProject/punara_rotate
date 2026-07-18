"""Typed reads the API serves verbatim — exact `data` payloads of CONTRACTS §3.

Everything reads DuckDB (marts) except where a SQLite Session parameter is
declared: customer_detail (PII join), scores_latest / score_history
(score_runs). overview_kpis opens its own short-lived SQLite session for the
scores block so its contract signature stays (tenant_id) -> dict.

customers_page returns the full envelope {"data", "page", "page_size",
"total"}; every other function returns the inner `data` value.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .olap import get_conn

SCORE_NAMES = (
    "gravity", "flow", "signal", "watertight",
    "vitals", "velocity", "autopilot", "pulse", "altitude",
)
PHASE2_SCORES = ("vitals", "velocity", "autopilot", "pulse", "altitude")


def _composite_name(runs: dict) -> str:
    """`ciq` once the v2 engine has written one (or nothing ran yet);
    `ciq_partial` only for pre-v2 DBs that never got a full ciq row."""
    return "ciq" if "ciq" in runs or "ciq_partial" not in runs else "ciq_partial"


def _iso(dt: datetime | None) -> str | None:
    return None if dt is None else dt.isoformat() + "Z"  # storage is naive UTC


def _month(d: date | None) -> str | None:
    return None if d is None else f"{d:%Y-%m}"


# --------------------------------------------------------------------------- overview


def overview_kpis(tenant_id: int) -> dict:
    con = get_conn()
    try:
        as_of = con.execute(
            "SELECT MAX(placed_at) FROM fact_orders "
            "WHERE tenant_id = $t AND cancelled_at IS NULL",
            {"t": tenant_id},
        ).fetchone()[0]
        agg = con.execute(
            """
            WITH b AS (SELECT date_trunc('month', MAX(placed_at))::DATE AS mmax
                       FROM fact_orders WHERE tenant_id = $t AND cancelled_at IS NULL)
            SELECT COALESCE(SUM(total_revenue_paise), 0),
                   COALESCE(SUM(repeat_revenue_paise), 0),
                   COALESCE(SUM(orders), 0)
            FROM executive_kpis, b
            WHERE tenant_id = $t AND month > b.mmax - INTERVAL 12 MONTH
            """,
            {"t": tenant_id},
        ).fetchone()
        total_rev, repeat_rev, orders = int(agg[0]), int(agg[1]), int(agg[2])
        customers = con.execute(
            "SELECT COUNT(*) FROM rfm_current WHERE tenant_id = $t", {"t": tenant_id}
        ).fetchone()[0]
        last = con.execute(
            "SELECT new_customers FROM executive_kpis WHERE tenant_id = $t "
            "ORDER BY month DESC LIMIT 1",
            {"t": tenant_id},
        ).fetchone()
        leak = con.execute(
            """
            WITH b AS (SELECT date_trunc('month', MAX(placed_at))::DATE AS mmax
                       FROM fact_orders WHERE tenant_id = $t AND cancelled_at IS NULL)
            SELECT COALESCE(SUM(amount_paise), 0) FROM leak_facts, b
            WHERE tenant_id = $t AND month > b.mmax - INTERVAL 12 MONTH
            """,
            {"t": tenant_id},
        ).fetchone()[0]
    finally:
        con.close()

    from .db import get_session  # local import: keeps DuckDB-only callers cheap

    with get_session() as session:
        runs = _latest_runs(session, tenant_id)
    return {
        "as_of": _iso(as_of),
        "window_months": 12,
        "total_revenue_paise": total_rev,
        "repeat_revenue_paise": repeat_rev,
        "repeat_rate": (repeat_rev / total_rev) if total_rev else 0.0,
        "orders": orders,
        "customers": int(customers),
        "new_customers_last_month": int(last[0]) if last else 0,
        "aov_paise": (total_rev // orders) if orders else 0,
        "leak_total_paise": int(leak),
        "scores": {
            name: (runs[name].value if name in runs else None)
            for name in SCORE_NAMES + (_composite_name(runs),)
        },
    }


# --------------------------------------------------------------------------- cohorts


def cohort_matrix(tenant_id: int) -> dict:
    con = get_conn()
    try:
        rows = con.execute(
            """
            SELECT cohort_month, months_since, cohort_size, active_customers,
                   retention_rate, repeat_revenue_paise
            FROM cohort_retention WHERE tenant_id = $t
            ORDER BY cohort_month, months_since
            """,
            {"t": tenant_id},
        ).fetchall()
    finally:
        con.close()
    cohorts: dict[str, dict] = {}
    for cm, ms, size, active, rate, rrev in rows:
        key = _month(cm)
        c = cohorts.setdefault(key, {"cohort_month": key, "cohort_size": int(size), "cells": []})
        c["cells"].append(
            {
                "months_since": int(ms),
                "active_customers": int(active),
                "retention_rate": float(rate),
                "repeat_revenue_paise": int(rrev),
            }
        )
    return {"cohorts": list(cohorts.values())}


# --------------------------------------------------------------------------- rfm


def rfm_grid(tenant_id: int) -> dict:
    con = get_conn()
    try:
        as_of = con.execute(
            "SELECT MAX(as_of) FROM rfm_current WHERE tenant_id = $t", {"t": tenant_id}
        ).fetchone()[0]
        segs = con.execute(
            """
            SELECT rfm_segment, COUNT(*), SUM(monetary_paise),
                   CAST(ROUND(AVG(recency_days)) AS BIGINT),
                   ROUND(AVG(frequency), 1),
                   CAST(AVG(monetary_paise) AS BIGINT)
            FROM rfm_current WHERE tenant_id = $t
            GROUP BY rfm_segment ORDER BY SUM(monetary_paise) DESC
            """,
            {"t": tenant_id},
        ).fetchall()
        grid = con.execute(
            """
            SELECT r_quintile, f_quintile, COUNT(*), SUM(monetary_paise)
            FROM rfm_current WHERE tenant_id = $t
            GROUP BY r_quintile, f_quintile
            ORDER BY r_quintile DESC, f_quintile DESC
            """,
            {"t": tenant_id},
        ).fetchall()
    finally:
        con.close()
    return {
        "as_of": str(as_of) if as_of else None,
        "segments": [
            {
                "segment": s,
                "customers": int(n),
                "revenue_paise": int(rev),
                "avg_recency_days": int(ar),
                "avg_frequency": float(af),
                "avg_monetary_paise": int(am),
            }
            for s, n, rev, ar, af, am in segs
        ],
        "grid": [
            {
                "r_quintile": int(r),
                "f_quintile": int(f),
                "customers": int(n),
                "revenue_paise": int(rev),
            }
            for r, f, n, rev in grid
        ],
    }


# --------------------------------------------------------------------------- revenue


def revenue_monthly(tenant_id: int) -> list[dict]:
    con = get_conn()
    try:
        rows = con.execute(
            """
            SELECT month, total_revenue_paise, repeat_revenue_paise, orders,
                   new_customers, returning_customers, repeat_rate, aov_paise
            FROM executive_kpis WHERE tenant_id = $t ORDER BY month
            """,
            {"t": tenant_id},
        ).fetchall()
    finally:
        con.close()
    return [
        {
            "month": _month(m),
            "revenue_paise": int(rev),
            "repeat_revenue_paise": int(rrev),
            "orders": int(n),
            "new_customers": int(newc),
            "returning_customers": int(retc),
            "repeat_rate": float(rate),
            "aov_paise": int(aov),
        }
        for m, rev, rrev, n, newc, retc, rate, aov in rows
    ]


# ------------------------------------------------------------------------- campaigns


def campaign_roi(tenant_id: int) -> list[dict]:
    """campaign_roi mart rows, verbatim (CONTRACTS §3 /campaigns)."""
    con = get_conn()
    try:
        rows = con.execute(
            """
            SELECT campaign_id, campaign_name, channel, campaign_type, sends,
                   delivered, unique_opens, unique_clicks, unsubscribes, bounces,
                   attributed_orders, attributed_revenue_paise, revenue_per_message_paise
            FROM campaign_roi WHERE tenant_id = $t
            ORDER BY attributed_revenue_paise DESC, campaign_id
            """,
            {"t": tenant_id},
        ).fetchall()
    finally:
        con.close()
    keys = (
        "campaign_id", "campaign_name", "channel", "campaign_type", "sends",
        "delivered", "unique_opens", "unique_clicks", "unsubscribes", "bounces",
        "attributed_orders", "attributed_revenue_paise", "revenue_per_message_paise",
    )
    return [
        {k: (v if isinstance(v, str) else int(v)) for k, v in zip(keys, row)}
        for row in rows
    ]


# --------------------------------------------------------------------------- leaks


def leaks_summary(tenant_id: int) -> dict:
    con = get_conn()
    try:
        params = {"t": tenant_id}
        window = """
            WITH b AS (SELECT date_trunc('month', MAX(placed_at))::DATE AS mmax
                       FROM fact_orders WHERE tenant_id = $t AND cancelled_at IS NULL)
        """
        by_type = con.execute(
            window
            + """
            SELECT leak_type, SUM(amount_paise), SUM(orders_affected)
            FROM leak_facts, b
            WHERE tenant_id = $t AND month > b.mmax - INTERVAL 12 MONTH
            GROUP BY leak_type ORDER BY SUM(amount_paise) DESC
            """,
            params,
        ).fetchall()
        revenue = con.execute(
            window
            + """
            SELECT COALESCE(SUM(total_revenue_paise), 0) FROM executive_kpis, b
            WHERE tenant_id = $t AND month > b.mmax - INTERVAL 12 MONTH
            """,
            params,
        ).fetchone()[0]
        monthly = con.execute(
            window
            + """
            SELECT month, leak_type, amount_paise FROM leak_facts, b
            WHERE tenant_id = $t AND month > b.mmax - INTERVAL 12 MONTH
            ORDER BY month, leak_type
            """,
            params,
        ).fetchall()
    finally:
        con.close()
    revenue = int(revenue)
    total = sum(int(a) for _, a, _ in by_type)
    return {
        "window_months": 12,
        "total_paise": total,
        "annualized_paise": total,  # window is 12 months, so annualized == total
        "revenue_share": (total / revenue) if revenue else 0.0,
        "leaks": [
            {
                "leak_type": lt,
                "amount_paise": int(amt),
                "orders_affected": int(n),
                "revenue_share": (int(amt) / revenue) if revenue else 0.0,
            }
            for lt, amt, n in by_type
        ],
        "monthly": [
            {"month": _month(m), "leak_type": lt, "amount_paise": int(amt)}
            for m, lt, amt in monthly
        ],
    }


# --------------------------------------------------------------------------- customers


def customers_page(
    tenant_id: int,
    segment: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    where = "r.tenant_id = $t"
    params: dict = {"t": tenant_id}
    if segment:
        where += " AND r.rfm_segment = $seg"
        params["seg"] = segment
    con = get_conn()
    try:
        total = con.execute(
            f"SELECT COUNT(*) FROM rfm_current r WHERE {where}", params
        ).fetchone()[0]
        rows = con.execute(
            f"""
            SELECT r.customer_id, c.lifecycle_stage, r.rfm_segment, c.orders_count,
                   c.total_spent_paise, c.first_order_at, c.last_order_at,
                   r.recency_days, c.whatsapp_opted_in
            FROM rfm_current r
            JOIN dim_customers c
              ON c.tenant_id = r.tenant_id AND c.customer_id = r.customer_id
            WHERE {where}
            ORDER BY c.last_order_at DESC NULLS LAST, r.customer_id
            LIMIT $lim OFFSET $off
            """,
            {**params, "lim": page_size, "off": (page - 1) * page_size},
        ).fetchall()
    finally:
        con.close()
    return {
        "data": [
            {
                "id": int(cid),
                "lifecycle_stage": stage,
                "rfm_segment": seg,
                "orders_count": int(n),
                "total_spent_paise": int(spent),
                "first_order_at": _iso(first),
                "last_order_at": _iso(last),
                "recency_days": int(rec),
                "whatsapp_opted_in": bool(wa),
            }
            for cid, stage, seg, n, spent, first, last, rec, wa in rows
        ],
        "page": page,
        "page_size": page_size,
        "total": int(total),
    }


def customer_detail(session: Session, tenant_id: int, customer_id: int) -> dict | None:
    """The only read that touches PII — straight from SQLite, never DuckDB."""
    cust = session.get(models.Customer, customer_id)
    if cust is None or cust.tenant_id != tenant_id:
        return None
    pii = session.get(models.CustomerPII, customer_id)
    identities = session.scalars(
        select(models.CustomerIdentity)
        .where(
            models.CustomerIdentity.tenant_id == tenant_id,
            models.CustomerIdentity.customer_id == customer_id,
        )
        .order_by(models.CustomerIdentity.id)
    ).all()
    orders = session.scalars(
        select(models.Order)
        .where(
            models.Order.tenant_id == tenant_id,
            models.Order.customer_id == customer_id,
        )
        .order_by(models.Order.placed_at.desc())
    ).all()
    tickets = session.scalars(
        select(models.SupportTicket)
        .where(
            models.SupportTicket.tenant_id == tenant_id,
            models.SupportTicket.customer_id == customer_id,
        )
        .order_by(models.SupportTicket.opened_at.desc())
    ).all()
    reviews = session.scalars(
        select(models.Review)
        .where(
            models.Review.tenant_id == tenant_id,
            models.Review.customer_id == customer_id,
        )
        .order_by(models.Review.submitted_at.desc())
    ).all()
    nps = session.scalars(
        select(models.NpsResponse)
        .where(
            models.NpsResponse.tenant_id == tenant_id,
            models.NpsResponse.customer_id == customer_id,
        )
        .order_by(models.NpsResponse.responded_at.desc())
    ).all()
    con = get_conn()
    try:
        seg = con.execute(
            "SELECT rfm_segment FROM rfm_current WHERE tenant_id = $t AND customer_id = $c",
            {"t": tenant_id, "c": customer_id},
        ).fetchone()
    finally:
        con.close()
    name = " ".join(p for p in [pii.first_name if pii else None, pii.last_name if pii else None] if p)
    return {
        "id": cust.id,
        "name": name or None,
        "email": pii.primary_email if pii else None,
        "phone": pii.primary_phone if pii else None,
        "lifecycle_stage": cust.lifecycle_stage,
        "rfm_segment": seg[0] if seg else None,
        "orders_count": cust.orders_count,
        "total_spent_paise": cust.total_spent_paise,
        "first_order_at": _iso(cust.first_order_at),
        "last_order_at": _iso(cust.last_order_at),
        "consent": {
            "email": bool(cust.accepts_email_marketing),
            "whatsapp": bool(cust.whatsapp_opted_in),
            "sms": bool(cust.sms_opted_in),
        },
        "identities": [
            {"identity_type": i.identity_type, "identity_value": i.identity_value}
            for i in identities
        ],
        "orders": [
            {
                "id": o.id,
                "order_number": o.order_number,
                "placed_at": _iso(o.placed_at),
                "total_paise": o.total_paise,
                "cod": bool(o.cod),
                "financial_status": o.financial_status,
                "fulfillment_status": o.fulfillment_status,
            }
            for o in orders
        ],
        # Phase 2 (CONTRACTS V2.7): prediction block, null before the first ml
        # run; ticket/review/nps rows for the customer timeline (SQLite-only —
        # free text stays out of DuckDB, this endpoint already serves PII).
        "prediction": customer_prediction(session, tenant_id, customer_id),
        "tickets": [
            {
                "id": tk.id,
                "subject": tk.subject,
                "category": tk.category,
                "status": tk.status,
                "opened_at": _iso(tk.opened_at),
                "resolved_at": _iso(tk.resolved_at),
                "csat": tk.csat,
            }
            for tk in tickets
        ],
        "reviews": [
            {
                "id": rv.id,
                "rating": rv.rating,
                "title": rv.title,
                "verified": bool(rv.verified),
                "submitted_at": _iso(rv.submitted_at),
            }
            for rv in reviews
        ],
        "nps": [
            {"id": n.id, "score": n.score, "responded_at": _iso(n.responded_at)}
            for n in nps
        ],
    }


# --------------------------------------------------------------------------- scores


def _latest_runs(session: Session, tenant_id: int) -> dict[str, models.ScoreRun]:
    runs = session.scalars(
        select(models.ScoreRun)
        .where(models.ScoreRun.tenant_id == tenant_id)
        .order_by(models.ScoreRun.computed_at, models.ScoreRun.id)
    ).all()
    return {r.score: r for r in runs}  # later runs overwrite earlier -> latest wins


def scores_latest(session: Session, tenant_id: int) -> dict:
    latest = _latest_runs(session, tenant_id)
    composite = _composite_name(latest)
    entries = []
    for name in SCORE_NAMES + (composite,):
        r = latest.get(name)
        if r is not None:
            status = "computed"
        elif name in PHASE2_SCORES:
            status = "phase_2"  # engine hasn't written this score yet
        else:
            status = "pending"  # pipeline not run yet
        entries.append(
            {
                "score": name,
                "value": r.value if r else None,
                "status": status,
                "components": dict(r.components) if r else {},
            }
        )
    computed_at = max((r.computed_at for r in latest.values()), default=None)
    if composite in latest:
        version = latest[composite].definition_version
    else:
        version = next(iter(latest.values())).definition_version if latest else "v0.1"
    return {
        "computed_at": _iso(computed_at),
        "definition_version": version,
        "scores": entries,
    }


def score_history(session: Session, tenant_id: int, score: str) -> list[dict]:
    runs = session.scalars(
        select(models.ScoreRun)
        .where(
            models.ScoreRun.tenant_id == tenant_id,
            models.ScoreRun.score == score,
        )
        .order_by(models.ScoreRun.computed_at, models.ScoreRun.id)
    ).all()
    return [
        {
            "computed_at": _iso(r.computed_at),
            "value": r.value,
            "definition_version": r.definition_version,
        }
        for r in runs
    ]


# ============================================================ Phase 2 (CONTRACTS v2)
# --------------------------------------------------------------------------- cx


def cx_summary(tenant_id: int) -> list[dict]:
    """cx_facts rows, monthly ascending (V2.7 /cx)."""
    con = get_conn()
    try:
        rows = con.execute(
            """
            SELECT month, orders_delivered, median_delivery_days, rto_orders,
                   rto_rate, tickets_opened, ticket_rate, median_resolution_hours,
                   breach_rate, avg_csat, reviews, avg_review_rating,
                   nps_responses, nps
            FROM cx_facts WHERE tenant_id = $t ORDER BY month
            """,
            {"t": tenant_id},
        ).fetchall()
    finally:
        con.close()
    return [
        {
            "month": _month(m),
            "orders_delivered": int(dlv),
            "median_delivery_days": None if med_d is None else float(med_d),
            "rto_orders": int(rto),
            "rto_rate": None if rto_r is None else float(rto_r),
            "tickets_opened": int(tik),
            "ticket_rate": None if tik_r is None else float(tik_r),
            "median_resolution_hours": None if med_h is None else float(med_h),
            "breach_rate": None if br is None else float(br),
            "avg_csat": None if csat is None else float(csat),
            "reviews": int(rv),
            "avg_review_rating": None if rr is None else float(rr),
            "nps_responses": int(nn),
            "nps": None if nps is None else float(nps),
        }
        for m, dlv, med_d, rto, rto_r, tik, tik_r, med_h, br, csat, rv, rr, nn, nps
        in rows
    ]


# ------------------------------------------------------------------------ messaging


def messaging_summary(tenant_id: int) -> dict:
    """messaging_facts rows + trailing-12mo whatsapp_summary (V2.7 /messaging)."""
    con = get_conn()
    try:
        rows = con.execute(
            """
            SELECT month, channel, sends, delivered, opened_or_read, clicked,
                   bounced, bounce_rate, unsubscribed, attributed_orders,
                   attributed_revenue_paise, revenue_per_message_paise
            FROM messaging_facts WHERE tenant_id = $t ORDER BY month, channel
            """,
            {"t": tenant_id},
        ).fetchall()
        wa = con.execute(
            """
            WITH b AS (SELECT MAX(month) AS mmax FROM messaging_facts WHERE tenant_id = $t)
            SELECT COALESCE(SUM(sends), 0), COALESCE(SUM(delivered), 0),
                   COALESCE(SUM(opened_or_read), 0), COALESCE(SUM(clicked), 0),
                   COALESCE(SUM(attributed_revenue_paise), 0)
            FROM messaging_facts, b
            WHERE tenant_id = $t AND channel = 'whatsapp'
              AND month > b.mmax - INTERVAL 12 MONTH
            """,
            {"t": tenant_id},
        ).fetchone()
    finally:
        con.close()
    sends, delivered, read, clicked, rev = (int(x) for x in wa)
    return {
        "months": [
            {
                "month": _month(m),
                "channel": ch,
                "sends": int(s),
                "delivered": int(d),
                "opened_or_read": int(o),
                "clicked": int(c),
                "bounced": int(b),
                "bounce_rate": float(br),
                "unsubscribed": int(u),
                "attributed_orders": int(ao),
                "attributed_revenue_paise": int(ar),
                "revenue_per_message_paise": int(rpm),
            }
            for m, ch, s, d, o, c, b, br, u, ao, ar, rpm in rows
        ],
        "whatsapp_summary": {
            "sends": sends,
            "read_rate": (read / delivered) if delivered else 0.0,
            "reply_rate": (clicked / delivered) if delivered else 0.0,
            "attributed_revenue_paise": rev,
            "revenue_per_conversation_paise": (rev // delivered) if delivered else 0,
        },
    }


# ----------------------------------------------------------------------- automation


def automation_summary(tenant_id: int) -> list[dict]:
    """automation_facts rows in canonical moment order."""
    from .marts import MOMENTS  # single source of the moment vocabulary

    con = get_conn()
    try:
        rows = con.execute(
            """
            SELECT moment, covered, campaign_id, sends, attributed_orders,
                   attributed_revenue_paise, automated_revenue_share
            FROM automation_facts WHERE tenant_id = $t
            """,
            {"t": tenant_id},
        ).fetchall()
    finally:
        con.close()
    by_moment = {r[0]: r for r in rows}
    return [
        {
            "moment": m,
            "covered": bool(r[1]),
            "campaign_id": None if r[2] is None else int(r[2]),
            "sends": int(r[3]),
            "attributed_orders": int(r[4]),
            "attributed_revenue_paise": int(r[5]),
            "automated_revenue_share": float(r[6]),
        }
        for m in MOMENTS
        if (r := by_moment.get(m)) is not None
    ]


# ---------------------------------------------------------------------- experiments


def experiments_list(session: Session, tenant_id: int) -> list[dict]:
    """experiments table rows verbatim, newest started_at first, drafts last
    (V2.7 /experiments). SQLite — hypothesis free text never enters DuckDB."""
    exps = session.scalars(
        select(models.Experiment)
        .where(models.Experiment.tenant_id == tenant_id)
        .order_by(
            models.Experiment.started_at.desc().nullslast(),
            models.Experiment.id.desc(),
        )
    ).all()
    return [
        {
            "id": e.id,
            "name": e.name,
            "hypothesis": e.hypothesis,
            "score_target": e.score_target,
            "status": e.status,
            "started_at": _iso(e.started_at),
            "concluded_at": _iso(e.concluded_at),
            "sample_size": e.sample_size,
            "lift_pct": e.lift_pct,
            "significant": e.significant,
            "decision": e.decision,
        }
        for e in exps
    ]


def experiment_cadence(tenant_id: int) -> list[dict]:
    """Experiments started per month (non-draft), derived from experiment_facts
    (V2.5: cadence is a GROUP BY, not a second mart)."""
    con = get_conn()
    try:
        rows = con.execute(
            """
            SELECT started_month, COUNT(*) FROM experiment_facts
            WHERE tenant_id = $t AND started_month IS NOT NULL AND status != 'draft'
            GROUP BY 1 ORDER BY 1
            """,
            {"t": tenant_id},
        ).fetchall()
    finally:
        con.close()
    return [{"month": _month(m), "experiments": int(n)} for m, n in rows]


# ---------------------------------------------------------------------- predictions


def predictions_summary(
    session: Session,
    tenant_id: int,
    page: int = 1,
    page_size: int = 50,
) -> dict | None:
    """V2.7 /predictions payload from SQLite predictions (latest run) +
    rfm_current/dim_customers labels. None before the first ml run (API 404s)."""
    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    latest = session.execute(
        select(models.Prediction.model_version, models.Prediction.scored_on)
        .where(models.Prediction.tenant_id == tenant_id)
        .order_by(models.Prediction.scored_at.desc(), models.Prediction.id.desc())
        .limit(1)
    ).first()
    if latest is None:
        return None
    model_version, scored_on = latest
    preds = session.scalars(
        select(models.Prediction).where(
            models.Prediction.tenant_id == tenant_id,
            models.Prediction.model_version == model_version,
            models.Prediction.scored_on == scored_on,
        )
    ).all()

    band_counts: dict[str, int] = {}
    for p in preds:
        band_counts[p.churn_band] = band_counts.get(p.churn_band, 0) + 1
    ltvs = sorted(p.ltv_12m_paise for p in preds)
    deciles = [int(ltvs[(i * len(ltvs)) // 10]) for i in range(10)] if ltvs else []
    high = sorted(
        (p for p in preds if p.churn_band == "high"),
        key=lambda p: (-p.ltv_12m_paise, p.customer_id),
    )
    page_rows = high[(page - 1) * page_size : page * page_size]

    labels: dict[int, tuple] = {}
    if page_rows:
        con = get_conn()
        try:
            ids = ", ".join(str(p.customer_id) for p in page_rows)
            got = con.execute(
                f"""
                SELECT c.customer_id, r.rfm_segment, c.lifecycle_stage,
                       c.orders_count, c.total_spent_paise
                FROM dim_customers c
                LEFT JOIN rfm_current r
                  ON r.tenant_id = c.tenant_id AND r.customer_id = c.customer_id
                WHERE c.tenant_id = $t AND c.customer_id IN ({ids})
                """,
                {"t": tenant_id},
            ).fetchall()
        finally:
            con.close()
        labels = {int(row[0]): row for row in got}

    def _row(p: models.Prediction) -> dict:
        lab = labels.get(p.customer_id)
        return {
            "customer_id": p.customer_id,
            "p_alive": p.p_alive,
            "expected_orders_90d": p.expected_orders_90d,
            "ltv_12m_paise": p.ltv_12m_paise,
            "churn_band": p.churn_band,
            "rfm_segment": lab[1] if lab else None,
            "lifecycle_stage": lab[2] if lab else None,
            "orders_count": int(lab[3]) if lab else None,
            "total_spent_paise": int(lab[4]) if lab else None,
        }

    return {
        "model_version": model_version,
        "scored_at": _iso(max(p.scored_at for p in preds)),
        "customers_scored": len(preds),
        "band_counts": band_counts,
        "expected_orders_90d_total": float(sum(p.expected_orders_90d for p in preds)),
        "ltv_12m_deciles_paise": deciles,
        "at_risk_ltv_paise": sum(p.ltv_12m_paise for p in high),
        "top_risk": [_row(p) for p in page_rows],
        "page": page,
        "page_size": page_size,
        "total": len(high),
    }


def customer_prediction(session: Session, tenant_id: int, customer_id: int) -> dict | None:
    """Latest prediction for one customer (customer_detail's `prediction` block)."""
    p = session.scalars(
        select(models.Prediction)
        .where(
            models.Prediction.tenant_id == tenant_id,
            models.Prediction.customer_id == customer_id,
        )
        .order_by(models.Prediction.scored_at.desc(), models.Prediction.id.desc())
        .limit(1)
    ).first()
    if p is None:
        return None
    return {
        "p_alive": p.p_alive,
        "expected_orders_90d": p.expected_orders_90d,
        "ltv_12m_paise": p.ltv_12m_paise,
        "churn_band": p.churn_band,
        "model_version": p.model_version,
        "scored_at": _iso(p.scored_at),
    }


# ------------------------------------------------------- scorer-input assemblers
# Plain-dict ingredients for the five Phase-2 scorers (CONTRACTS V2.4). The
# scores builder calls these from gather_inputs; each dict is JSON-serializable
# so inputs_hash works unchanged. Windows are anchored on data clocks (max
# month in the mart), never wall clock.


def vitals_inputs(tenant_id: int) -> dict:
    con = get_conn()
    t = {"t": tenant_id}
    try:
        email = con.execute(
            """
            WITH b AS (SELECT MAX(month) AS mmax FROM messaging_facts WHERE tenant_id = $t)
            SELECT SUM(bounced) * 1.0 / NULLIF(SUM(sends), 0),
                   SUM(unsubscribed) * 1.0 / NULLIF(SUM(sends), 0)
            FROM messaging_facts, b
            WHERE tenant_id = $t AND channel = 'email' AND month > b.mmax - INTERVAL 6 MONTH
            """,
            t,
        ).fetchone()
        wa_fail = con.execute(
            """
            WITH b AS (SELECT MAX(month) AS mmax FROM messaging_facts WHERE tenant_id = $t)
            SELECT SUM(bounced) * 1.0 / NULLIF(SUM(sends), 0)
            FROM messaging_facts, b
            WHERE tenant_id = $t AND channel = 'whatsapp' AND month > b.mmax - INTERVAL 6 MONTH
            """,
            t,
        ).fetchone()[0]
        optin = con.execute(
            "SELECT AVG(CASE WHEN whatsapp_opted_in THEN 1.0 ELSE 0.0 END) "
            "FROM dim_customers WHERE tenant_id = $t",
            t,
        ).fetchone()[0]
        consent_backed = con.execute(
            """
            WITH flags AS (
              SELECT customer_id, 'email' AS channel FROM dim_customers
              WHERE tenant_id = $t AND accepts_email_marketing
              UNION ALL SELECT customer_id, 'whatsapp' FROM dim_customers
              WHERE tenant_id = $t AND whatsapp_opted_in
              UNION ALL SELECT customer_id, 'sms' FROM dim_customers
              WHERE tenant_id = $t AND sms_opted_in
            ),
            last_c AS (
              SELECT customer_id, channel, action FROM fact_consent
              WHERE tenant_id = $t
              QUALIFY ROW_NUMBER() OVER (PARTITION BY customer_id, channel
                                         ORDER BY occurred_at DESC, consent_id DESC) = 1
            )
            SELECT AVG(CASE WHEN lc.action = 'granted' THEN 1.0 ELSE 0.0 END)
            FROM flags f LEFT JOIN last_c lc USING (customer_id, channel)
            """,
            t,
        ).fetchone()[0]
        sends_after_revoke = con.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT c.action,
                     ROW_NUMBER() OVER (PARTITION BY m.message_id
                                        ORDER BY c.occurred_at DESC, c.consent_id DESC) AS rn
              FROM fact_messages m
              JOIN fact_consent c
                ON c.tenant_id = m.tenant_id AND c.customer_id = m.customer_id
               AND c.channel = m.channel AND c.occurred_at <= m.sent_at
              WHERE m.tenant_id = $t
            ) WHERE rn = 1 AND action = 'revoked'
            """,
            t,
        ).fetchone()[0]
        total_sends = con.execute(
            "SELECT COUNT(*) FROM fact_messages WHERE tenant_id = $t", t
        ).fetchone()[0]
        flows = con.execute(
            """
            WITH clock AS (SELECT MAX(sent_at) AS mx FROM fact_messages WHERE tenant_id = $t),
            f AS (
              SELECT dc.campaign_id, MAX(m.sent_at) AS last_send
              FROM dim_campaigns dc
              LEFT JOIN fact_messages m
                ON m.tenant_id = $t AND m.campaign_id = dc.campaign_id
              WHERE dc.tenant_id = $t AND dc.campaign_type = 'flow'
              GROUP BY 1
            )
            SELECT COUNT(*),
                   COUNT(*) FILTER (WHERE last_send >= mx - INTERVAL 60 DAY)
            FROM f CROSS JOIN clock
            """,
            t,
        ).fetchone()
    finally:
        con.close()
    return {
        "email_bounce_rate": None if email[0] is None else float(email[0]),
        "email_unsub_rate": None if email[1] is None else float(email[1]),
        "whatsapp_optin_share": float(optin or 0.0),
        "whatsapp_fail_rate": None if wa_fail is None else float(wa_fail),
        "consent_backed_share": None if consent_backed is None else float(consent_backed),
        "sends_after_revoke": int(sends_after_revoke),
        "total_sends": int(total_sends),
        "flows_total": int(flows[0]),
        "flows_active_60d": int(flows[1]),
    }


def velocity_inputs(tenant_id: int) -> dict:
    con = get_conn()
    t = {"t": tenant_id}
    try:
        cadence = con.execute(
            """
            WITH b AS (SELECT MAX(started_month) AS mmax FROM experiment_facts
                       WHERE tenant_id = $t)
            SELECT started_month, COUNT(*) FROM experiment_facts, b
            WHERE tenant_id = $t AND status != 'draft'
              AND started_month > b.mmax - INTERVAL 6 MONTH
            GROUP BY 1 ORDER BY 1
            """,
            t,
        ).fetchall()
        concluded = con.execute(
            """
            SELECT COUNT(*),
                   COUNT(*) FILTER (WHERE significant IS NOT NULL AND sample_size >= 1000),
                   COUNT(*) FILTER (WHERE decision IN ('shipped', 'killed'))
            FROM experiment_facts WHERE tenant_id = $t AND status = 'concluded'
            """,
            t,
        ).fetchone()
    finally:
        con.close()
    return {
        "window_months": 6,
        "monthly_starts": {_month(m): int(n) for m, n in cadence},
        "concluded": int(concluded[0]),
        "concluded_valid": int(concluded[1]),
        "concluded_decided": int(concluded[2]),
    }


def autopilot_inputs(tenant_id: int) -> dict:
    moments = automation_summary(tenant_id)
    con = get_conn()
    try:
        perf = con.execute(
            """
            SELECT campaign_type,
                   SUM(attributed_revenue_paise) // NULLIF(SUM(sends), 0)
            FROM campaign_roi WHERE tenant_id = $t GROUP BY 1
            """,
            {"t": tenant_id},
        ).fetchall()
    finally:
        con.close()
    rpm = {ctype: (None if v is None else int(v)) for ctype, v in perf}
    return {
        "moments": moments,
        "moments_total": len(moments),
        "moments_covered": sum(1 for m in moments if m["covered"]),
        "automated_revenue_share": sum(
            m["automated_revenue_share"] for m in moments if m["covered"]
        ),
        "flow_revenue_per_send_paise": rpm.get("flow"),
        "campaign_revenue_per_send_paise": rpm.get("campaign"),
    }


def pulse_inputs(tenant_id: int) -> dict:
    con = get_conn()
    t = {"t": tenant_id}
    try:
        row = con.execute(
            """
            WITH b AS (SELECT MAX(month) AS mmax FROM cx_facts WHERE tenant_id = $t)
            SELECT median(median_delivery_days),
                   SUM(rto_orders) * 1.0
                     / NULLIF(SUM(orders_delivered) + SUM(rto_orders), 0),
                   AVG(median_resolution_hours), AVG(breach_rate), AVG(avg_csat),
                   SUM(avg_review_rating * reviews) / NULLIF(SUM(reviews), 0),
                   SUM(nps * nps_responses) / NULLIF(SUM(nps_responses), 0)
            FROM cx_facts, b
            WHERE tenant_id = $t AND month > b.mmax - INTERVAL 6 MONTH
            """,
            t,
        ).fetchone()
        prev_rating = con.execute(
            """
            WITH b AS (SELECT MAX(month) AS mmax FROM cx_facts WHERE tenant_id = $t)
            SELECT SUM(avg_review_rating * reviews) / NULLIF(SUM(reviews), 0)
            FROM cx_facts, b
            WHERE tenant_id = $t AND month <= b.mmax - INTERVAL 6 MONTH
              AND month > b.mmax - INTERVAL 12 MONTH
            """,
            t,
        ).fetchone()[0]
    finally:
        con.close()
    keys = (
        "median_delivery_days", "rto_rate", "median_resolution_hours",
        "breach_rate", "avg_csat", "avg_review_rating", "nps",
    )
    out = {k: (None if v is None else float(v)) for k, v in zip(keys, row)}
    out["avg_review_rating_prev_6mo"] = None if prev_rating is None else float(prev_rating)
    return out


def altitude_inputs(session: Session, tenant_id: int) -> dict:
    from sqlalchemy import func

    predictions_rows = session.scalar(
        select(func.count())
        .select_from(models.Prediction)
        .where(models.Prediction.tenant_id == tenant_id)
    ) or 0
    pred_latest = session.scalar(
        select(func.max(models.Prediction.scored_on)).where(
            models.Prediction.tenant_id == tenant_id
        )
    )
    # Freshness vs run wall clock: run metadata, like score_runs.computed_at.
    predictions_fresh = (
        pred_latest is not None and (datetime.utcnow().date() - pred_latest).days <= 7
    )
    run_months = sorted(
        {
            f"{d:%Y-%m}"
            for (d,) in session.execute(
                select(models.ScoreRun.computed_at).where(
                    models.ScoreRun.tenant_id == tenant_id
                )
            )
        }
    )
    streak = 0
    if run_months:
        streak = 1
        recent = run_months[::-1]  # newest first
        for later, earlier in zip(recent, recent[1:]):
            y1, m1 = (int(x) for x in later.split("-"))
            y0, m0 = (int(x) for x in earlier.split("-"))
            if y1 * 12 + m1 - (y0 * 12 + m0) == 1:
                streak += 1
            else:
                break
    con = get_conn()
    try:
        marts_built = con.execute(
            "SELECT COUNT(*) FROM rfm_current WHERE tenant_id = $t", {"t": tenant_id}
        ).fetchone()[0]
        as_of = con.execute(
            "SELECT MAX(placed_at) FROM fact_orders WHERE tenant_id = $t",
            {"t": tenant_id},
        ).fetchone()[0]
    finally:
        con.close()
    # Experiments from SQLite (system of record; hypothesis never mirrored to
    # DuckDB), windowed on the data clock (max order timestamp).
    exps = session.scalars(
        select(models.Experiment).where(models.Experiment.tenant_id == tenant_id)
    ).all()
    concluded = [e for e in exps if e.status == "concluded"]
    six_mo_ago = None if as_of is None else as_of - timedelta(days=180)
    vel = velocity_inputs(tenant_id)
    vit = vitals_inputs(tenant_id)
    return {
        "predictions_rows": int(predictions_rows),
        "predictions_fresh": bool(predictions_fresh),
        "marts_built": bool(marts_built),
        "scores_ever_run": bool(run_months),
        "monthly_run_streak": int(streak),
        "concluded_6mo": sum(
            1
            for e in concluded
            if e.concluded_at is not None and six_mo_ago is not None and e.concluded_at >= six_mo_ago
        ),
        "winners_shipped": sum(1 for e in concluded if e.decision == "shipped"),
        "decided_share": (
            sum(1 for e in concluded if e.hypothesis and e.decision) / len(concluded)
            if concluded
            else None
        ),
        "cadence_starts_6mo": sum(vel["monthly_starts"].values()),
        "flows_total": vit["flows_total"],
        "flows_active_60d": vit["flows_active_60d"],
    }
