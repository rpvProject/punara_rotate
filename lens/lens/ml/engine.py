"""ML engine: nightly batch predictions (CONTRACTS.md V2.3, blueprint 08 §7).

Pipeline: fact_orders (DuckDB) -> per-customer (frequency, recency, T) in
weeks -> BG/NBD fit (p_alive, expected orders 90d/12m) -> Gamma-Gamma on
repeat purchasers (expected order value; single-order customers get the
population prior per CONTRACTS V2.3) -> ltv_12m_paise (12m expected orders x
expected value, discounted 10%/yr mid-year convention, capped at the cohort
p99 to stop outlier blowups) -> churn bands from p_alive at the pinned
CONTRACTS V2.3 thresholds (high < 0.35 <= medium < 0.65 <= low) ->
predictions upsert. A gradient-boosted classifier still trains as a SHADOW
diagnostic (leakage-safe features, time-based AUC logged against the floor)
so the named upgrade path stays measurable — it never sets bands.

Upsert key: (tenant_id, customer_id, model_version, scored_on); a same-day
re-run replaces that day's rows, a new day appends (drift stays measurable).
``scored_at`` is run wall-clock metadata; every model INPUT is anchored to
the data (as_of = max order timestamp) — no wall-clock features.

Stack (final, per CONTRACTS V2.3): BG/NBD + Gamma-Gamma in-repo via
scipy.optimize (``lifetimes`` is unmaintained); churn via sklearn
HistGradientBoostingClassifier — xgboost rejected (Windows native-DLL
friction for zero v2 gain). Deterministic: fixed optimizer starts, fixed
random_state, no sampling.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from ..models import Prediction, SupportTicket
from . import bgnbd, churn

MODEL_VERSION = "bgnbd-0.1+palive-bands-0.1"  # bands are p_alive thresholds (CONTRACTS V2.3)
_WEEK_SECONDS = 7.0 * 86400.0
_DISCOUNT_12M = 1.10 ** -0.5  # 10%/yr, mid-year convention (revenue accrues over the year)
_MIN_REPEATERS = 10


@dataclass(frozen=True)
class MlReport:
    tenant_id: int
    model_version: str
    customers_scored: int
    band_counts: dict[str, int]  # churn_band -> customers


def run(session: Session, tenant_id: int) -> MlReport:
    from .. import olap  # lazy: analytics agent owns olap.py (v0 scores-engine pattern)

    t = tenant_id
    con = olap.get_conn()
    try:
        orders = con.execute(
            """SELECT customer_id, placed_at, total_paise, discount_paise, subtotal_paise
               FROM fact_orders
               WHERE tenant_id = ? AND customer_id IS NOT NULL
                 AND cancelled_at IS NULL AND placed_at IS NOT NULL
               ORDER BY customer_id, placed_at""",
            [t],
        ).fetchall()
        categories = con.execute(
            """SELECT o.customer_id, o.placed_at, coalesce(p.product_type, 'unknown')
               FROM fact_order_items i
               JOIN fact_orders o ON o.tenant_id = i.tenant_id AND o.order_id = i.order_id
               LEFT JOIN dim_products p ON p.tenant_id = i.tenant_id AND p.product_id = i.product_id
               WHERE i.tenant_id = ? AND o.customer_id IS NOT NULL AND o.cancelled_at IS NULL""",
            [t],
        ).fetchall()
        rtos = con.execute(
            """SELECT o.customer_id, coalesce(s.rto_at, s.delivered_at, s.shipped_at)
               FROM fact_shipments s
               JOIN fact_orders o ON o.tenant_id = s.tenant_id AND o.order_id = s.order_id
               WHERE s.tenant_id = ? AND s.rto AND o.customer_id IS NOT NULL""",
            [t],
        ).fetchall()
        messages = con.execute(
            """SELECT customer_id, sent_at, opened_at, clicked_at
               FROM fact_messages WHERE tenant_id = ? AND customer_id IS NOT NULL""",
            [t],
        ).fetchall()
    finally:
        con.close()
    if not orders:
        raise ValueError(
            f"ml: tenant {t} has no resolved orders in fact_orders — run export_core first"
        )
    # support tickets live in SQLite core (fact_tickets is the analytics
    # builder's DuckDB seam and may not exist yet — core table is guaranteed).
    tickets = session.execute(
        select(SupportTicket.customer_id, SupportTicket.opened_at).where(
            SupportTicket.tenant_id == t, SupportTicket.customer_id.is_not(None)
        )
    ).all()

    # ---- per-customer RFM/T in weeks, anchored to the data (no wall clock)
    per: dict[int, list[tuple]] = defaultdict(list)
    for cid, placed, total, *_ in orders:
        per[cid].append((placed, total or 0))
    cids = sorted(per)
    as_of = max(row[1] for row in orders)
    n_orders = np.array([len(per[c]) for c in cids], dtype=float)
    firsts = [per[c][0][0] for c in cids]  # rows arrive ORDER BY customer_id, placed_at
    lasts = [per[c][-1][0] for c in cids]
    x = n_orders - 1.0  # repeat transactions
    t_x = np.array([(l - f).total_seconds() for f, l in zip(firsts, lasts)]) / _WEEK_SECONDS
    T = np.array([(as_of - f).total_seconds() for f in firsts]) / _WEEK_SECONDS
    mean_value = np.maximum(
        np.array([sum(r[1] for r in per[c]) for c in cids]) / n_orders, 1.0
    )
    if int((x > 0).sum()) < _MIN_REPEATERS:
        raise ValueError(
            f"ml: tenant {t} has under {_MIN_REPEATERS} repeat purchasers — too little signal to fit BG/NBD"
        )

    # ---- BG/NBD
    params = bgnbd.fit_bgnbd(x, t_x, T)
    palive = bgnbd.p_alive(params, x, t_x, T)
    e90 = bgnbd.expected_orders(params, x, t_x, T, 90.0 / 7.0)
    e12m = bgnbd.expected_orders(params, x, t_x, T, 365.0 / 7.0)

    # ---- Gamma-Gamma on repeaters; independence assumption check (FH13):
    # the model assumes order value ⟂ frequency — corr(x, m̄) must be small.
    rep = x > 0
    corr = float(np.corrcoef(n_orders[rep], mean_value[rep])[0, 1]) if rep.sum() > 2 else 0.0
    print(
        f"ml: gamma-gamma independence check corr(frequency, avg order value) = {corr:.3f}"
        + (" — WARNING: |corr| > 0.3, monetary fit is strained" if abs(corr) > 0.3 else " (ok)")
    )
    gg = bgnbd.fit_gamma_gamma(n_orders[rep], mean_value[rep])
    if gg.q > 1.0:
        prior = gg.p * gg.v / (gg.q - 1.0)  # population mean order value
        cond = bgnbd.expected_order_value(gg, n_orders, mean_value)
    else:
        # ponytail: degenerate GG fit (q<=1 -> infinite prior mean); fall back
        # to observed means. Upgrade path: penalized MLE if this ever triggers.
        prior = float(np.average(mean_value[rep], weights=n_orders[rep]))
        cond = mean_value
    exp_value = np.where(n_orders >= 2, cond, prior)  # singles: population prior (V2.3)

    # ---- LTV: 12m expected orders x expected value, discounted, p99-capped
    ltv = e12m * exp_value * _DISCOUNT_12M
    cap = float(np.quantile(ltv, 0.99))
    ltv_paise = [int(round(min(float(v), cap))) for v in ltv]

    # ---- churn bands: p_alive thresholds (CONTRACTS V2.3). The classifier is
    # a shadow diagnostic: time-split AUC logged so the feature-based upgrade
    # path stays measurable; it never sets bands.
    raw = dict(
        orders=orders, categories=categories, rtos=rtos,
        tickets=tickets, messages=messages,
    )
    cut_valid = as_of - timedelta(days=churn.HORIZON_DAYS)
    cut_train = as_of - timedelta(days=2 * churn.HORIZON_DAYS)
    try:
        _, auc = churn.train(
            churn.build_features(cut_train, **raw),
            churn.build_labels(cut_train, orders),
            churn.build_features(cut_valid, **raw),
            churn.build_labels(cut_valid, orders),
        )
        print(
            f"ml: shadow churn classifier time-split auc {auc:.3f}"
            f" (floor {churn.AUC_FLOOR}; bands stay p_alive-thresholded per CONTRACTS V2.3)"
        )
    except ValueError as exc:
        print(f"ml: shadow churn classifier skipped ({exc})")
    version = MODEL_VERSION
    band_by_cid = churn.bands({c: float(p) for c, p in zip(cids, palive)})

    # ---- upsert (V2.0 semantics). Deleting by (tenant, scored_on) alone also
    # clears an earlier same-day run that wrote a different version string,
    # so a day never carries mixed-version rows.
    scored_at = datetime.utcnow()
    scored_on = scored_at.date()
    session.execute(
        delete(Prediction).where(Prediction.tenant_id == t, Prediction.scored_on == scored_on)
    )
    session.execute(
        insert(Prediction),
        [
            {
                "tenant_id": t,
                "customer_id": cid,
                "p_alive": float(palive[i]),
                "expected_orders_90d": float(e90[i]),
                "ltv_12m_paise": ltv_paise[i],
                "churn_band": band_by_cid[cid],
                "model_version": version,
                "scored_at": scored_at,
                "scored_on": scored_on,
            }
            for i, cid in enumerate(cids)
        ],
    )
    session.commit()
    return MlReport(
        tenant_id=t,
        model_version=version,
        customers_scored=len(cids),
        band_counts=dict(Counter(band_by_cid[c] for c in cids)),
    )
