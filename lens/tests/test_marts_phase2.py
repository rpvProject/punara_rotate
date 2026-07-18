"""Phase-2 analytics tests on a tiny handcrafted fixture — one exact
hand-computed number per new mart (CONTRACTS V2.5), plus the new typed reads.

Env vars point settings at throwaway files and must be set before any lens
import (same pattern as tests/test_marts.py).
"""

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="lens_marts_p2_test_"))
os.environ["LENS_DB_URL"] = "sqlite:///" + (_TMP / "test.db").as_posix()
os.environ["LENS_OLAP_PATH"] = (_TMP / "test.duckdb").as_posix()

from datetime import date, datetime, timedelta  # noqa: E402

import pytest  # noqa: E402

import lens  # noqa: E402
from lens import marts, olap  # noqa: E402
from lens import queries  # noqa: E402
from lens.config import settings  # noqa: E402
from lens.db import get_session, init_db  # noqa: E402
from lens.models import (  # noqa: E402
    Campaign,
    Customer,
    Experiment,
    Message,
    NpsResponse,
    Order,
    Prediction,
    Review,
    Shipment,
    SupportTicket,
    Tenant,
)

# Shared-suite guard: tests/test_api.py injects a fake lens.queries into
# sys.modules. If the fake is installed, load the real module from disk.
if not getattr(queries, "__file__", None):
    import importlib.util

    _spec = importlib.util.spec_from_file_location(
        "lens._real_queries_p2", Path(lens.__file__).with_name("queries.py")
    )
    queries = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(queries)

D = datetime


@pytest.fixture(scope="module")
def fixture():
    """Seed core rows directly, run export + marts once, return (tenant_id, ids)."""
    settings.olap_path = (_TMP / "test.duckdb").as_posix()
    init_db()
    with get_session() as s:
        t = Tenant(slug="p2-fixture", name="Phase2 Fixture")
        s.add(t)
        s.flush()
        tid = t.id

        c1 = Customer(tenant_id=tid, source="shopify", external_id="c1",
                      whatsapp_opted_in=True, accepts_email_marketing=True)
        c2 = Customer(tenant_id=tid, source="shopify", external_id="c2",
                      accepts_email_marketing=True)
        s.add_all([c1, c2])
        s.flush()

        # orders: O3 (C2 first, Apr, COD -> RTO in May); O2 (C2 second, May 4);
        # O1 (C1 first, May 5).
        o3 = Order(tenant_id=tid, customer_id=c2.id, source="shopify", external_id="o3",
                   placed_at=D(2026, 4, 2), total_paise=50000, subtotal_paise=50000,
                   financial_status="pending", cod=True, customer_order_index=1)
        o2 = Order(tenant_id=tid, customer_id=c2.id, source="shopify", external_id="o2",
                   placed_at=D(2026, 5, 4), total_paise=60000, subtotal_paise=60000,
                   financial_status="paid", customer_order_index=2)
        o1 = Order(tenant_id=tid, customer_id=c1.id, source="shopify", external_id="o1",
                   placed_at=D(2026, 5, 5), total_paise=90000, subtotal_paise=90000,
                   financial_status="paid", customer_order_index=1)
        s.add_all([o3, o2, o1])
        s.flush()

        # shipments: O1 delivered in May (3 days in transit); O3 RTO'd in May.
        s.add(Shipment(tenant_id=tid, order_id=o1.id, source="shiprocket",
                       external_id="sh1", status="delivered",
                       shipped_at=D(2026, 5, 6), delivered_at=D(2026, 5, 9)))
        s.add(Shipment(tenant_id=tid, order_id=o3.id, source="shiprocket",
                       external_id="sh2", status="rto_received", rto=True,
                       shipped_at=D(2026, 4, 4), rto_at=D(2026, 5, 2)))

        # campaigns: one klaviyo welcome flow (KLF-01), one email blast,
        # one interakt whatsapp campaign.
        flow = Campaign(tenant_id=tid, source="klaviyo", external_id="KLF-01",
                        name="Welcome Series", campaign_type="flow", channel="email",
                        started_at=D(2026, 1, 1))
        blast = Campaign(tenant_id=tid, source="klaviyo", external_id="K-C1",
                         name="Blast", campaign_type="campaign", channel="email",
                         started_at=D(2026, 4, 1))
        wa = Campaign(tenant_id=tid, source="interakt", external_id="WA-1",
                      name="WA Push", campaign_type="campaign", channel="whatsapp",
                      started_at=D(2026, 5, 1))
        s.add_all([flow, blast, wa])
        s.flush()

        def msg(ext, camp, cust, channel, sent, **ts):
            return Message(tenant_id=tid, campaign_id=camp.id, customer_id=cust.id,
                           channel=channel, source=camp.source, external_id=ext,
                           sent_at=sent, **ts)

        s.add_all([
            # April email blast to C1: clicked Apr 1 — outside 7d of O1 (May 5).
            msg("e-blast", blast, c1, "email", D(2026, 4, 1),
                delivered_at=D(2026, 4, 1), opened_at=D(2026, 4, 1),
                clicked_at=D(2026, 4, 1)),
            # May flow email to C2: clicked May 1 -> wins O2 (May 4).
            msg("e-flow", flow, c2, "email", D(2026, 5, 1),
                delivered_at=D(2026, 5, 1), opened_at=D(2026, 5, 1),
                clicked_at=D(2026, 5, 1)),
            # May whatsapp: 4 sends, 3 delivered, 2 read, 1 replied, 1 failed.
            msg("w1", wa, c1, "whatsapp", D(2026, 5, 1),
                delivered_at=D(2026, 5, 1), opened_at=D(2026, 5, 2),
                clicked_at=D(2026, 5, 3)),  # wins O1 (May 5)
            msg("w2", wa, c2, "whatsapp", D(2026, 5, 1),
                delivered_at=D(2026, 5, 1), opened_at=D(2026, 5, 1)),
            msg("w3", wa, c2, "whatsapp", D(2026, 5, 2), delivered_at=D(2026, 5, 2)),
            msg("w4", wa, c1, "whatsapp", D(2026, 5, 2), bounced_at=D(2026, 5, 2)),
        ])

        # tickets resolved in May: 10h / 20h / 100h -> median 20h, breach 1/3.
        for ext, opened, hours, csat in (
            ("t1", D(2026, 5, 10), 10, 4),
            ("t2", D(2026, 5, 12), 20, 5),
            ("t3", D(2026, 5, 14), 100, None),
        ):
            s.add(SupportTicket(tenant_id=tid, customer_id=c2.id, order_id=o3.id,
                                source="gorgias", external_id=ext, channel="email",
                                category="delivery_delay", status="resolved",
                                opened_at=opened,
                                first_response_at=opened + timedelta(hours=1),
                                resolved_at=opened + timedelta(hours=hours),
                                csat=csat))

        # reviews in May: 5 and 4 -> avg 4.5.
        s.add(Review(tenant_id=tid, customer_id=c1.id, order_id=o1.id,
                     source="judgeme", external_id="r1", rating=5, title="Great",
                     verified=True, submitted_at=D(2026, 5, 12)))
        s.add(Review(tenant_id=tid, customer_id=c2.id, order_id=o2.id,
                     source="judgeme", external_id="r2", rating=4,
                     verified=True, submitted_at=D(2026, 5, 20)))

        # nps in May: 10, 9, 7, 3 -> 50% promoters - 25% detractors = 25.0.
        for ext, score in (("n1", 10), ("n2", 9), ("n3", 7), ("n4", 3)):
            s.add(NpsResponse(tenant_id=tid, customer_id=c1.id, source="punara",
                              external_id=ext, score=score,
                              channel="post_purchase_widget",
                              responded_at=D(2026, 5, 15)))

        # experiments: one concluded in 30 days, one running, one draft.
        s.add(Experiment(tenant_id=tid, name="COD nudge", hypothesis="h",
                         score_target="watertight", status="concluded",
                         started_at=D(2026, 3, 1), concluded_at=D(2026, 3, 31),
                         sample_size=2000, lift_pct=8.0, significant=True,
                         decision="shipped"))
        s.add(Experiment(tenant_id=tid, name="Winback copy", hypothesis="h",
                         score_target="gravity", status="running",
                         started_at=D(2026, 5, 10)))
        s.add(Experiment(tenant_id=tid, name="Someday", hypothesis="h",
                         score_target="flow", status="draft"))

        # predictions (SQLite only — never exported).
        s.add(Prediction(tenant_id=tid, customer_id=c1.id, p_alive=0.2,
                         expected_orders_90d=0.1, ltv_12m_paise=84000,
                         churn_band="high", model_version="v2.0",
                         scored_at=D(2026, 7, 17, 2, 0), scored_on=date(2026, 7, 17)))
        s.add(Prediction(tenant_id=tid, customer_id=c2.id, p_alive=0.8,
                         expected_orders_90d=1.2, ltv_12m_paise=231000,
                         churn_band="low", model_version="v2.0",
                         scored_at=D(2026, 7, 17, 2, 0), scored_on=date(2026, 7, 17)))
        s.commit()

        ids = {"C1": c1.id, "C2": c2.id}
        olap.export_core(s, tid)
    marts.build(tid)
    return tid, ids


def test_cx_facts_exact(fixture):
    tid, _ = fixture
    may = next(r for r in queries.cx_summary(tid) if r["month"] == "2026-05")
    assert may["orders_delivered"] == 1
    assert may["median_delivery_days"] == pytest.approx(3.0)
    assert may["rto_orders"] == 1
    assert may["rto_rate"] == pytest.approx(0.5)  # 1 RTO / (1 delivered + 1 RTO)
    assert may["tickets_opened"] == 3
    assert may["ticket_rate"] == pytest.approx(1.5)  # 3 tickets / 2 May orders
    assert may["median_resolution_hours"] == pytest.approx(20.0)
    assert may["breach_rate"] == pytest.approx(1 / 3)  # only the 100h ticket
    assert may["avg_csat"] == pytest.approx(4.5)
    assert may["reviews"] == 2 and may["avg_review_rating"] == pytest.approx(4.5)
    assert may["nps_responses"] == 4 and may["nps"] == pytest.approx(25.0)


def test_messaging_facts_whatsapp_exact(fixture):
    tid, _ = fixture
    data = queries.messaging_summary(tid)
    wa_may = next(r for r in data["months"]
                  if r["month"] == "2026-05" and r["channel"] == "whatsapp")
    assert wa_may["sends"] == 4 and wa_may["delivered"] == 3
    assert wa_may["opened_or_read"] == 2 and wa_may["clicked"] == 1
    assert wa_may["bounced"] == 1 and wa_may["bounce_rate"] == pytest.approx(0.25)
    assert wa_may["attributed_orders"] == 1
    assert wa_may["attributed_revenue_paise"] == 90000
    # revenue-per-conversation (Bet 6): 90000 attributed / 3 delivered
    assert wa_may["revenue_per_message_paise"] == 30000
    ws = data["whatsapp_summary"]
    assert ws["revenue_per_conversation_paise"] == 30000
    assert ws["read_rate"] == pytest.approx(2 / 3)
    # email in May: flow click wins O2
    em_may = next(r for r in data["months"]
                  if r["month"] == "2026-05" and r["channel"] == "email")
    assert em_may["attributed_revenue_paise"] == 60000


def test_automation_facts_exact(fixture):
    tid, _ = fixture
    rows = {r["moment"]: r for r in queries.automation_summary(tid)}
    assert set(rows) == {"welcome", "post_purchase", "winback", "replenishment",
                         "cod_confirmation", "abandoned_checkout"}
    welcome = rows["welcome"]
    assert welcome["covered"] is True and welcome["campaign_id"] is not None
    assert welcome["sends"] == 1 and welcome["attributed_orders"] == 1
    assert welcome["attributed_revenue_paise"] == 60000
    # 60000 flow-attributed of 150000 total message-attributed (60000 + 90000 WA)
    assert welcome["automated_revenue_share"] == pytest.approx(0.4)
    assert sum(1 for r in rows.values() if r["covered"]) == 1  # only welcome
    assert rows["replenishment"]["covered"] is False
    assert rows["replenishment"]["campaign_id"] is None


def test_experiment_facts_exact(fixture):
    tid, _ = fixture
    con = olap.get_conn()
    try:
        rows = con.execute(
            "SELECT name, status, started_month, days_to_decision "
            "FROM experiment_facts WHERE tenant_id = ? ORDER BY experiment_id",
            [tid],
        ).fetchall()
    finally:
        con.close()
    assert len(rows) == 3
    cod = next(r for r in rows if r[0] == "COD nudge")
    assert cod[1] == "concluded" and str(cod[2]) == "2026-03-01"
    assert cod[3] == 30  # 2026-03-01 -> 2026-03-31
    draft = next(r for r in rows if r[0] == "Someday")
    assert draft[2] is None and draft[3] is None
    # cadence derives from the mart: one non-draft start in March, one in May
    cadence = {c["month"]: c["experiments"] for c in queries.experiment_cadence(tid)}
    assert cadence == {"2026-03": 1, "2026-05": 1}


def test_experiments_list_order(fixture):
    tid, _ = fixture
    with get_session() as s:
        exps = queries.experiments_list(s, tid)
    assert [e["name"] for e in exps] == ["Winback copy", "COD nudge", "Someday"]
    assert exps[1]["decision"] == "shipped" and exps[1]["lift_pct"] == 8.0
    assert exps[2]["started_at"] is None  # draft last


def test_predictions_summary_exact(fixture):
    tid, ids = fixture
    with get_session() as s:
        data = queries.predictions_summary(s, tid)
        assert data["band_counts"] == {"high": 1, "low": 1}
        assert data["customers_scored"] == 2 and data["total"] == 1
        assert data["at_risk_ltv_paise"] == 84000
        top = data["top_risk"][0]
        assert top["customer_id"] == ids["C1"] and top["churn_band"] == "high"
        assert top["rfm_segment"] is not None  # joined from rfm_current
        one = queries.customer_prediction(s, tid, ids["C2"])
        assert one["ltv_12m_paise"] == 231000 and one["churn_band"] == "low"
        assert queries.customer_prediction(s, tid, 10**9) is None
        assert queries.predictions_summary(s, tid + 999) is None


def test_scorer_input_assemblers_shapes(fixture):
    tid, _ = fixture
    v = queries.vitals_inputs(tid)
    assert v["flows_total"] == 1 and v["flows_active_60d"] == 1
    assert v["whatsapp_optin_share"] == pytest.approx(0.5)  # C1 of 2
    assert v["sends_after_revoke"] == 0  # no consent rows -> no revokes
    assert v["total_sends"] >= 1  # violation-rate denominator for vitals.score
    vel = queries.velocity_inputs(tid)
    assert vel["concluded"] == 1 and vel["concluded_valid"] == 1
    assert vel["concluded_decided"] == 1
    ap = queries.autopilot_inputs(tid)
    assert ap["moments_covered"] == 1 and ap["moments_total"] == 6
    assert ap["automated_revenue_share"] == pytest.approx(0.4)
    p = queries.pulse_inputs(tid)
    assert p["rto_rate"] == pytest.approx(0.5) and p["nps"] == pytest.approx(25.0)
    with get_session() as s:
        alt = queries.altitude_inputs(s, tid)
    assert alt["predictions_rows"] == 2 and alt["marts_built"] is True
    assert alt["scores_ever_run"] is False
    # everything altitude.score consumes is present (CONTRACTS V2.9 seam)
    assert set(alt) >= {
        "predictions_fresh", "concluded_6mo", "winners_shipped", "decided_share",
        "cadence_starts_6mo", "flows_total", "flows_active_60d", "monthly_run_streak",
    }


def test_new_events_exported(fixture):
    tid, _ = fixture
    con = olap.get_conn()
    try:
        counts = dict(con.execute(
            """
            SELECT event_name, COUNT(*) FROM events WHERE tenant_id = ?
              AND event_name IN ('ticket_opened', 'ticket_resolved',
                                 'review_submitted', 'nps_submitted',
                                 'experiment_concluded')
            GROUP BY 1
            """,
            [tid],
        ).fetchall())
    finally:
        con.close()
    assert counts == {"ticket_opened": 3, "ticket_resolved": 3,
                      "review_submitted": 2, "nps_submitted": 4,
                      "experiment_concluded": 1}


def test_rebuild_is_idempotent(fixture):
    tid, _ = fixture
    before = (queries.cx_summary(tid), queries.messaging_summary(tid),
              queries.automation_summary(tid))
    with get_session() as s:
        olap.export_core(s, tid)
    marts.build(tid)
    marts.build(tid)
    after = (queries.cx_summary(tid), queries.messaging_summary(tid),
             queries.automation_summary(tid))
    assert after == before
