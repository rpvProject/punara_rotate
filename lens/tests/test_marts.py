"""Analytics-layer tests on a tiny handcrafted fixture (12 customers, known orders).

Every expected number below is hand-computed from the fixture — if a mart
formula drifts, these fail. Env vars point settings at throwaway files and
must be set before any lens import.
"""

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="lens_marts_test_"))
os.environ["LENS_DB_URL"] = "sqlite:///" + (_TMP / "test.db").as_posix()
os.environ["LENS_OLAP_PATH"] = (_TMP / "test.duckdb").as_posix()

from datetime import datetime  # noqa: E402

import pytest  # noqa: E402

import lens  # noqa: E402
from lens import marts, olap  # noqa: E402
from lens import queries  # noqa: E402
from lens.config import settings  # noqa: E402
from lens.db import get_session, init_db  # noqa: E402
from lens.models import Customer, CustomerPII, Order, Payment, Shipment, Tenant  # noqa: E402

# Shared-suite guard: tests/test_api.py injects a fake lens.queries into
# sys.modules (written before this module existed on disk). If the fake is
# installed, load the real module directly from its file.
if not getattr(queries, "__file__", None):
    import importlib.util

    _spec = importlib.util.spec_from_file_location(
        "lens._real_queries", Path(lens.__file__).with_name("queries.py")
    )
    queries = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(queries)

D = datetime


def _order(tid, cid, ext, placed, total, oi, cod=False, subtotal=None, discount=0, fin="paid"):
    return Order(
        tenant_id=tid, customer_id=cid, source="shopify", external_id=ext,
        placed_at=placed, total_paise=total, subtotal_paise=subtotal if subtotal is not None else total,
        discount_paise=discount, financial_status=fin, cod=cod, customer_order_index=oi,
    )


@pytest.fixture(scope="module")
def fixture():
    """Seed core rows directly, run export + marts once, return (tenant_id, ids)."""
    # settings is a module-level singleton: if another test module imported
    # lens.config first (shared-suite run), re-pin the OLAP file to ours.
    settings.olap_path = (_TMP / "test.duckdb").as_posix()
    init_db()
    with get_session() as s:
        t = Tenant(slug="mart-fixture", name="Mart Fixture")
        s.add(t)
        s.flush()
        tid = t.id

        custs = {}
        for i in range(1, 13):
            c = Customer(tenant_id=tid, source="shopify", external_id=f"c{i}")
            s.add(c)
            custs[f"C{i}"] = c
        s.flush()
        ids = {k: c.id for k, c in custs.items()}

        # orders: (customer, ext, placed_at, total_paise, order_index, extras)
        orders = [
            # C1 champion: 5 orders, most recent overall (2026-06-20 = as_of)
            ("C1", "o1", D(2026, 1, 10), 100000, 1, {}),
            ("C1", "o2", D(2026, 2, 10), 100000, 2, {}),
            ("C1", "o3", D(2026, 3, 10), 100000, 3, {}),
            ("C1", "o4", D(2026, 4, 10), 100000, 4, {}),
            ("C1", "o5", D(2026, 6, 20), 100000, 5, {}),
            ("C2", "o6", D(2026, 1, 15), 200000, 1, {}),
            ("C2", "o7", D(2026, 2, 15), 150000, 2, {}),
            ("C3", "o8", D(2026, 1, 20), 120000, 1, {}),
            # C4 stalest single-order customer -> hibernating
            ("C4", "o9", D(2026, 1, 5), 80000, 1, {}),
            ("C5", "o10", D(2026, 2, 5), 110000, 1, {}),
            ("C6", "o11", D(2026, 2, 8), 95000, 1, {}),
            ("C6", "o12", D(2026, 3, 8), 105000, 1 + 1, {}),
            # C7: COD order that RTOs -> rto_cod leak 70000 in 2026-03
            ("C7", "o13", D(2026, 3, 5), 70000, 1, {"cod": True}),
            # C8: never-paid order with a failed payment -> failed_payments leak 60000
            ("C8", "o14", D(2026, 4, 5), 60000, 1, {"fin": "pending"}),
            ("C9", "o15", D(2026, 5, 5), 85000, 1, {}),
            # C10: discount 40% of subtotal -> abuse excess 10000 in 2026-06
            ("C10", "o16", D(2026, 6, 5), 60000, 1, {"subtotal": 100000, "discount": 40000}),
            ("C11", "o17", D(2026, 4, 10), 100000, 1, {}),
            ("C11", "o18", D(2026, 5, 10), 100000, 2, {}),
            ("C11", "o19", D(2026, 6, 10), 100000, 3, {}),
            ("C12", "o20", D(2026, 6, 1), 90000, 1, {}),
        ]
        order_rows = {}
        for cust, ext, placed, total, oi, extra in orders:
            o = _order(tid, ids[cust], ext, placed, total, oi, **extra)
            s.add(o)
            order_rows[ext] = o
        s.flush()

        s.add(Shipment(tenant_id=tid, order_id=order_rows["o13"].id, source="shiprocket",
                       external_id="sh1", status="rto_received", rto=True,
                       shipped_at=D(2026, 3, 7), rto_at=D(2026, 3, 12)))
        s.add(Payment(tenant_id=tid, order_id=order_rows["o14"].id, source="razorpay",
                      external_id="pay1", method="upi", status="failed",
                      amount_paise=60000, failure_reason="insufficient_funds",
                      occurred_at=D(2026, 4, 5)))

        # denormalized fields + PII for the detail endpoint check (C1)
        c1 = custs["C1"]
        c1.orders_count = 5
        c1.total_spent_paise = 500000
        c1.first_order_at = D(2026, 1, 10)
        c1.last_order_at = D(2026, 6, 20)
        c1.accepts_email_marketing = True
        s.add(CustomerPII(customer_id=ids["C1"], tenant_id=tid, primary_email="a@example.com",
                          primary_phone="+919876543210", first_name="Ananya", last_name="Iyer"))
        s.commit()

        olap.export_core(s, tid)
    marts.build(tid)
    return tid, ids


def test_revenue_month_exact(fixture):
    tid, _ = fixture
    feb = next(r for r in queries.revenue_monthly(tid) if r["month"] == "2026-02")
    # Feb orders: C1 100000 (repeat), C2 150000 (repeat), C5 110000, C6 95000
    assert feb["revenue_paise"] == 455000
    assert feb["repeat_revenue_paise"] == 250000
    assert feb["repeat_rate"] == pytest.approx(250000 / 455000)
    assert feb["orders"] == 4
    assert feb["new_customers"] == 2  # C5, C6
    assert feb["returning_customers"] == 2  # C1, C2
    assert feb["aov_paise"] == 455000 // 4


def test_cohort_cell_exact(fixture):
    tid, _ = fixture
    data = queries.cohort_matrix(tid)
    jan = next(c for c in data["cohorts"] if c["cohort_month"] == "2026-01")
    assert jan["cohort_size"] == 4  # C1..C4 first-ordered in Jan
    cell = next(x for x in jan["cells"] if x["months_since"] == 1)
    assert cell["active_customers"] == 2  # C1, C2 ordered again in Feb
    assert cell["retention_rate"] == pytest.approx(0.5)
    assert cell["repeat_revenue_paise"] == 250000
    m0 = next(x for x in jan["cells"] if x["months_since"] == 0)
    assert m0["active_customers"] == 4 and m0["retention_rate"] == pytest.approx(1.0)


def test_rfm_segment_assignment(fixture):
    tid, ids = fixture
    con = olap.get_conn()
    try:
        seg = dict(con.execute(
            "SELECT customer_id, rfm_segment FROM rfm_current WHERE tenant_id = ?", [tid]
        ).fetchall())
    finally:
        con.close()
    assert len(seg) == 12
    # strict max frequency + strict min recency -> quintile 5/5 regardless of ties
    assert seg[ids["C1"]] == "champions"
    # strict max recency + frequency 1 (lowest id among the 1-order tie) -> 1/1
    assert seg[ids["C4"]] == "hibernating"


def test_leak_paise_exact(fixture):
    tid, _ = fixture
    data = queries.leaks_summary(tid)
    by = {l["leak_type"]: l for l in data["leaks"]}
    assert by["rto_cod"]["amount_paise"] == 70000
    assert by["rto_cod"]["orders_affected"] == 1
    assert by["failed_payments"]["amount_paise"] == 60000
    assert by["discount_abuse"]["amount_paise"] == 10000  # 40000 - 30% of 100000
    assert by["preventable_churn"]["amount_paise"] > 0  # slipping customers exist by June
    assert data["total_paise"] == sum(l["amount_paise"] for l in data["leaks"])
    march_rto = next(m for m in data["monthly"]
                     if m["month"] == "2026-03" and m["leak_type"] == "rto_cod")
    assert march_rto["amount_paise"] == 70000


def test_customers_page_and_detail(fixture):
    tid, ids = fixture
    page = queries.customers_page(tid)
    assert page["total"] == 12 and len(page["data"]) == 12
    assert {"name", "email", "phone"}.isdisjoint(page["data"][0])  # no PII in lists
    champs = queries.customers_page(tid, segment="champions")
    assert champs["total"] == 2  # C1 and C11
    with get_session() as s:
        d = queries.customer_detail(s, tid, ids["C1"])
        assert d["name"] == "Ananya Iyer" and d["email"] == "a@example.com"
        assert d["rfm_segment"] == "champions" and len(d["orders"]) == 5
        assert d["consent"]["email"] is True and d["consent"]["sms"] is False
        assert queries.customer_detail(s, tid + 999, ids["C1"]) is None


def test_overview_and_scores_shapes(fixture):
    tid, _ = fixture
    ov = queries.overview_kpis(tid)
    assert ov["window_months"] == 12
    assert ov["orders"] == 20
    assert ov["customers"] == 12
    assert ov["as_of"] == "2026-06-20T00:00:00Z"
    # CONTRACTS V2.7: overview scores carry all nine + the composite (ciq once
    # the v2 engine exists; this fixture has no score runs, so values are None)
    assert set(ov["scores"]) == set(queries.SCORE_NAMES) | {"ciq"}
    with get_session() as s:
        sc = queries.scores_latest(s, tid)
        assert len(sc["scores"]) == 10
        assert sum(1 for e in sc["scores"] if e["status"] == "phase_2") == 5
        assert queries.score_history(s, tid, "gravity") == []


def test_rebuild_is_idempotent(fixture):
    tid, _ = fixture
    before = queries.leaks_summary(tid)
    with get_session() as s:
        olap.export_core(s, tid)
    marts.build(tid)
    marts.build(tid)
    assert queries.leaks_summary(tid) == before
