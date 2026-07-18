"""ML module tests: BG/NBD parameter recovery on a cohort simulated from the
model's own generative process, p_alive bounds/ranking, churn-feature
leakage safety, and the engine end-to-end (int paise LTV + same-day upsert).

The engine test builds its own tiny DuckDB (settings.olap_path monkeypatched
to tmp_path) + in-memory SQLite — no sibling agents' pipelines needed.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from lens.config import settings
from lens.ml import bgnbd, churn
from lens.ml import engine as ml_engine
from lens.models import Base, Prediction, Tenant

TRUE = {"r": 0.8, "alpha": 6.0, "a": 0.7, "b": 2.5}

# ------------------------------------------------------------------ BG/NBD


def _simulate_bgnbd(n: int = 2000, seed: int = 42):
    """Draw (x, t_x, T) from the BG/NBD generative story: lambda ~ Gamma(r, alpha),
    p ~ Beta(a, b), exponential inter-purchase times, dropout coin after each
    repeat purchase. Weeks."""
    rng = np.random.default_rng(seed)
    T = rng.uniform(40.0, 104.0, n)
    lam = np.maximum(rng.gamma(TRUE["r"], 1.0 / TRUE["alpha"], n), 1e-9)
    p = rng.beta(TRUE["a"], TRUE["b"], n)
    x = np.zeros(n)
    t_x = np.zeros(n)
    for i in range(n):
        t = rng.exponential(1.0 / lam[i])
        while t < T[i]:
            x[i] += 1
            t_x[i] = t
            if rng.random() < p[i]:
                break
            t += rng.exponential(1.0 / lam[i])
    return x, t_x, T


def test_bgnbd_recovers_known_parameters() -> None:
    x, t_x, T = _simulate_bgnbd()
    params = bgnbd.fit_bgnbd(x, t_x, T)
    assert params.r == pytest.approx(TRUE["r"], rel=0.30)
    assert params.alpha == pytest.approx(TRUE["alpha"], rel=0.35)
    # a and b are weakly identified individually; the mean dropout probability
    # a/(a+b) is the well-identified quantity.
    true_dropout = TRUE["a"] / (TRUE["a"] + TRUE["b"])
    assert params.a / (params.a + params.b) == pytest.approx(true_dropout, abs=0.08)

    palive = bgnbd.p_alive(params, x, t_x, T)
    assert np.all((palive >= 0.0) & (palive <= 1.0))
    e90 = bgnbd.expected_orders(params, x, t_x, T, 90.0 / 7.0)
    assert np.all(e90 >= 0.0)
    assert np.all(np.isfinite(e90))


def test_recent_frequent_buyer_outranks_stale_two_timer() -> None:
    params = bgnbd.BgNbdParams(**TRUE)
    # A: 10 orders over a year, latest ~a week ago (x=9, t_x=51, T=52).
    # B: 2 orders, both ~18 months ago (x=1, t_x=6, T=78).
    x, t_x, T = [9.0, 1.0], [51.0, 6.0], [52.0, 78.0]
    palive = bgnbd.p_alive(params, x, t_x, T)
    e90 = bgnbd.expected_orders(params, x, t_x, T, 90.0 / 7.0)
    assert palive[0] > palive[1]
    assert e90[0] > e90[1]
    assert np.all((palive >= 0.0) & (palive <= 1.0))


def test_gamma_gamma_expected_value_shrinks_to_prior() -> None:
    gg = bgnbd.GammaGammaParams(p=6.0, q=4.0, v=15.0)
    prior = gg.p * gg.v / (gg.q - 1.0)
    # zero observed orders -> exactly the population prior
    assert bgnbd.expected_order_value(gg, [0.0], [0.0])[0] == pytest.approx(prior)
    # heavy history -> pulled close to the observed mean
    heavy = bgnbd.expected_order_value(gg, [50.0], [100.0])[0]
    assert abs(heavy - 100.0) < abs(prior - 100.0)


# ------------------------------------------------------------------- churn


def test_churn_features_ignore_everything_after_cutoff() -> None:
    cutoff = datetime(2026, 1, 1)
    # truncated world: exactly what is knowable before the cutoff
    pre = dict(
        orders=[
            (1, datetime(2025, 3, 1), 50000, 5000, 55000),
            (1, datetime(2025, 11, 20), 70000, 0, 70000),
        ],
        categories=[(1, datetime(2025, 3, 1), "skincare")],
        rtos=[],
        tickets=[(1, datetime(2025, 12, 1))],
        messages=[
            (1, datetime(2025, 12, 15), datetime(2025, 12, 16), None),
            (1, datetime(2025, 12, 30), None, None),
        ],
    )
    # full world: same rows PLUS post-cutoff data — a new order, a new
    # category, an RTO, a ticket, a whole message, and (the sneaky case) an
    # open+click landing after the cutoff on a message sent before it.
    post = dict(
        orders=pre["orders"]
        + [(1, datetime(2026, 2, 1), 999999, 0, 999999), (2, datetime(2026, 3, 1), 88000, 0, 88000)],
        categories=pre["categories"] + [(1, datetime(2026, 2, 1), "haircare")],
        rtos=[(1, datetime(2026, 1, 5))],
        tickets=pre["tickets"] + [(1, datetime(2026, 1, 2))],
        messages=[
            (1, datetime(2025, 12, 15), datetime(2025, 12, 16), None),
            (1, datetime(2025, 12, 30), datetime(2026, 1, 2), datetime(2026, 1, 2)),
            (1, datetime(2026, 1, 3), datetime(2026, 1, 4), None),
        ],
    )
    f_pre = churn.build_features(cutoff, **pre)
    f_post = churn.build_features(cutoff, **post)
    assert f_pre == f_post  # nothing post-cutoff leaked into any feature
    assert 2 not in f_post  # customer born after the cutoff does not exist yet
    assert list(f_pre[1]) == pytest.approx(f_pre[1])  # vector is plain floats
    assert len(f_pre[1]) == len(churn.FEATURES)

    # labels: repeater with a post-cutoff order is retained (0); without it, churned (1)
    assert churn.build_labels(cutoff, post["orders"]) == {1: 0}
    assert churn.build_labels(cutoff, pre["orders"]) == {1: 1}


def test_bands_are_palive_thresholds() -> None:
    # CONTRACTS V2.3: high < 0.35 <= medium < 0.65 <= low, on p_alive
    assert churn.bands({1: 0.1, 2: 0.35, 3: 0.64, 4: 0.65, 5: 0.9}) == {
        1: "high",
        2: "medium",
        3: "medium",
        4: "low",
        5: "low",
    }


# ------------------------------------------------------------------ engine


@pytest.fixture()
def session(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "olap_path", str(tmp_path / "olap_test.duckdb"))
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Tenant(id=1, slug="ml-test", name="ML Test"))
        s.commit()
        yield s


def _seed_fact_orders(n_customers: int = 120, seed: int = 7) -> None:
    from lens import olap

    anchor = datetime(2026, 7, 1)
    rng = np.random.default_rng(seed)
    rows = []
    oid = 0
    for cid in range(1, n_customers + 1):
        start = anchor - timedelta(days=int(rng.integers(60, 540)))
        n = int(1 + rng.integers(1, 7)) if rng.random() < 0.6 else 1
        placed = start
        for k in range(n):
            if placed > anchor:
                break
            oid += 1
            total = int(rng.integers(30000, 300000))
            rows.append(
                (1, oid, cid, placed, None, None, None, "paid", "delivered", False,
                 total, 0, 0, 0, total, k + 1, None)
            )
            placed = placed + timedelta(days=float(rng.exponential(45.0) + 3.0))
    con = olap.get_conn()
    try:
        con.executemany(
            "INSERT INTO fact_orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows
        )
    finally:
        con.close()


def test_engine_writes_int_ltv_predictions_and_upserts(session) -> None:
    _seed_fact_orders()
    report = ml_engine.run(session, tenant_id=1)

    rows = session.query(Prediction).all()
    assert report.tenant_id == 1
    assert report.customers_scored == len(rows) > 0
    assert sum(report.band_counts.values()) == report.customers_scored
    assert set(report.band_counts) <= {"high", "medium", "low"}
    assert report.model_version.startswith("bgnbd-0.1")
    for r in rows:
        assert isinstance(r.ltv_12m_paise, int)  # money is integer paise
        assert r.ltv_12m_paise >= 0
        assert 0.0 <= r.p_alive <= 1.0
        assert r.expected_orders_90d >= 0.0
        assert r.churn_band in ("high", "medium", "low")
        assert r.scored_on == r.scored_at.date()

    # same-day re-run replaces in place — no row growth, same population
    report2 = ml_engine.run(session, tenant_id=1)
    assert session.query(Prediction).count() == report.customers_scored
    assert report2.customers_scored == report.customers_scored
