"""API contract tests: every endpoint 200s and validates against the response
models; unknown tenant/customer/score 404; pagination passes through.

lens.queries is NOT on disk yet (analytics agent owns it) — it is mocked here
with contract-shaped canned payloads injected into sys.modules. The routes
import it lazily (`import lens.queries as queries`) so the app imports fine
without it. SQLite-backed endpoints (tenants, meta, health, tenant resolution)
run against a real temp lens.db seeded below.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import types
from datetime import datetime
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="lens_api_test_"))
os.environ["LENS_DB_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["LENS_OLAP_PATH"] = (_TMP / "olap.duckdb").as_posix()
(_TMP / "olap.duckdb").touch()  # health only checks existence

import httpx  # noqa: E402

# ------------------------------------------------------------------ fake lens.queries

OVERVIEW = {
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
        "watertight": 44.1,
    },
}

SCORES_LATEST = {
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
                "repeat_revenue_share": 60.4,
            },
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
                "leak_total_paise": 9400000,
            },
        },
        {"score": "flow", "value": 54.0, "status": "computed", "components": {}},
        {"score": "signal", "value": 72.5, "status": "computed", "components": {}},
        {"score": "ciq_partial", "value": 58.4, "status": "computed", "components": {}},
        {"score": "vitals", "value": None, "status": "phase_2", "components": {}},
        {"score": "velocity", "value": None, "status": "phase_2", "components": {}},
        {"score": "autopilot", "value": None, "status": "phase_2", "components": {}},
        {"score": "pulse", "value": None, "status": "phase_2", "components": {}},
        {"score": "altitude", "value": None, "status": "phase_2", "components": {}},
    ],
}

HISTORY = [
    {"computed_at": "2026-06-01T02:00:00Z", "value": 59.8, "definition_version": "v0.1"},
    {"computed_at": "2026-07-01T02:00:00Z", "value": 61.2, "definition_version": "v0.1"},
]

COHORTS = {
    "cohorts": [
        {
            "cohort_month": "2025-01",
            "cohort_size": 380,
            "cells": [
                {"months_since": 0, "active_customers": 380, "retention_rate": 1.0, "repeat_revenue_paise": 0},
                {"months_since": 1, "active_customers": 72, "retention_rate": 0.189, "repeat_revenue_paise": 9210000},
            ],
        }
    ]
}

RFM = {
    "as_of": "2026-07-01",
    "segments": [
        {
            "segment": "champions",
            "customers": 512,
            "revenue_paise": 41200000,
            "avg_recency_days": 21,
            "avg_frequency": 6.2,
            "avg_monetary_paise": 80500,
        }
    ],
    "grid": [{"r_quintile": 5, "f_quintile": 5, "customers": 210, "revenue_paise": 18900000}],
}

REVENUE = [
    {
        "month": "2026-06",
        "revenue_paise": 15400000,
        "repeat_revenue_paise": 5100000,
        "orders": 1180,
        "new_customers": 402,
        "returning_customers": 231,
        "repeat_rate": 0.331,
        "aov_paise": 130500,
    }
]

LEAKS = {
    "window_months": 12,
    "total_paise": 9400000,
    "annualized_paise": 9400000,
    "revenue_share": 0.051,
    "leaks": [
        {"leak_type": "rto_cod", "amount_paise": 4100000, "orders_affected": 512, "revenue_share": 0.022},
        {"leak_type": "preventable_churn", "amount_paise": 3200000, "orders_affected": 0, "revenue_share": 0.017},
    ],
    "monthly": [{"month": "2026-06", "leak_type": "rto_cod", "amount_paise": 380000}],
}

CUSTOMER_ROW = {
    "id": 4211,
    "lifecycle_stage": "active",
    "rfm_segment": "loyal",
    "orders_count": 5,
    "total_spent_paise": 640000,
    "first_order_at": "2025-03-14T10:22:00Z",
    "last_order_at": "2026-06-02T18:40:00Z",
    "recency_days": 29,
    "whatsapp_opted_in": True,
}

CUSTOMER_DETAIL = {
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
    "consent": {"email": True, "whatsapp": True, "sms": False},
    "identities": [
        {"identity_type": "shopify_customer_id", "identity_value": "7712334221"},
        {"identity_type": "phone", "identity_value": "+919876543210"},
    ],
    "orders": [
        {
            "id": 88123,
            "order_number": "MB-10442",
            "placed_at": "2026-06-02T18:40:00Z",
            "total_paise": 145000,
            "cod": False,
            "financial_status": "paid",
            "fulfillment_status": "delivered",
        }
    ],
}

CALLS: dict[str, tuple] = {}

fake_queries = types.ModuleType("lens.queries")
fake_queries.overview_kpis = lambda tenant_id: OVERVIEW
fake_queries.cohort_matrix = lambda tenant_id: COHORTS
fake_queries.rfm_grid = lambda tenant_id: RFM
fake_queries.revenue_monthly = lambda tenant_id: REVENUE
fake_queries.leaks_summary = lambda tenant_id: LEAKS
fake_queries.scores_latest = lambda session, tenant_id: SCORES_LATEST
fake_queries.score_history = lambda session, tenant_id, score: HISTORY


def _customers_page(tenant_id, segment=None, page=1, page_size=50):
    CALLS["customers_page"] = (tenant_id, segment, page, page_size)
    return {"data": [CUSTOMER_ROW], "page": page, "page_size": page_size, "total": 9840}


def _customer_detail(session, tenant_id, customer_id):
    return CUSTOMER_DETAIL if customer_id == 4211 else None


fake_queries.customers_page = _customers_page
fake_queries.customer_detail = _customer_detail

# ---- Phase 2 (CONTRACTS V2.7) canned payloads ----

PREDICTIONS = {
    "model_version": "v2.0",
    "scored_at": "2026-07-17T02:10:00Z",
    "customers_scored": 9000,
    "band_counts": {"high": 812, "medium": 2404, "low": 5784},
    "expected_orders_90d_total": 1240.5,
    "ltv_12m_deciles_paise": [0, 9500, 21000, 36000, 54000, 78000, 108000, 152000, 231000, 480000],
    "at_risk_ltv_paise": 61200000,
    "top_risk": [
        {
            "customer_id": 4211, "p_alive": 0.12, "expected_orders_90d": 0.08,
            "ltv_12m_paise": 84000, "churn_band": "high",
            "rfm_segment": "cant_lose", "lifecycle_stage": "dormant",
            "orders_count": 6, "total_spent_paise": 812000,
        }
    ],
    "page": 1, "page_size": 50, "total": 812,
}

EXPERIMENTS = [
    {
        "id": 3, "name": "COD-to-prepaid nudge at checkout",
        "hypothesis": "A Rs.50 prepaid incentive cuts COD share 8pts.",
        "score_target": "watertight", "status": "concluded",
        "started_at": "2025-11-03T00:00:00Z", "concluded_at": "2025-12-03T00:00:00Z",
        "sample_size": 6300, "lift_pct": 15.0, "significant": True, "decision": "shipped",
    }
]

CX = [
    {
        "month": "2026-06", "orders_delivered": 500, "median_delivery_days": 4.0,
        "rto_orders": 40, "rto_rate": 0.074, "tickets_opened": 35, "ticket_rate": 0.065,
        "median_resolution_hours": 14.0, "breach_rate": 0.15, "avg_csat": 4.2,
        "reviews": 42, "avg_review_rating": 4.1, "nps_responses": 25, "nps": 35.0,
    }
]

MESSAGING = {
    "months": [
        {
            "month": "2026-06", "channel": "whatsapp", "sends": 1400, "delivered": 1330,
            "opened_or_read": 900, "clicked": 110, "bounced": 70, "bounce_rate": 0.05,
            "unsubscribed": 0, "attributed_orders": 60,
            "attributed_revenue_paise": 7200000, "revenue_per_message_paise": 5413,
        }
    ],
    "whatsapp_summary": {
        "sends": 1400, "read_rate": 0.68, "reply_rate": 0.08,
        "attributed_revenue_paise": 7200000, "revenue_per_conversation_paise": 5413,
    },
}

PRED_CALLS: dict[str, tuple] = {}


def _predictions_summary(session, tenant_id, page=1, page_size=50):
    PRED_CALLS["predictions_summary"] = (tenant_id, page, page_size)
    return None if tenant_id == 999 else PREDICTIONS


fake_queries.predictions_summary = _predictions_summary
fake_queries.experiments_list = lambda session, tenant_id: EXPERIMENTS
fake_queries.cx_summary = lambda tenant_id: CX
fake_queries.messaging_summary = lambda tenant_id: MESSAGING

sys.modules["lens.queries"] = fake_queries

# ------------------------------------------------------------------ real SQLite universe

import lens  # noqa: E402

lens.queries = fake_queries  # keep `from lens import queries` consistent too

from lens.db import get_session, init_db  # noqa: E402
from lens.models import ScoreRun, SyncState, Tenant  # noqa: E402

init_db()
with get_session() as _s:
    if _s.query(Tenant).filter_by(slug="meadow").first() is None:
        t = Tenant(
            slug="meadow",
            name="Meadow Botanicals",
            shopify_domain="meadow-botanicals.myshopify.com",
        )
        _s.add(t)
        _s.flush()
        _s.add_all(
            [
                SyncState(tenant_id=t.id, source="shopify", resource="orders",
                          cursor="raw:900", last_synced_at=datetime(2026, 7, 16, 2, 0)),
                SyncState(tenant_id=t.id, source="klaviyo", resource="messages",
                          cursor="raw:400", last_synced_at=datetime(2026, 7, 16, 2, 5)),
                ScoreRun(tenant_id=t.id, score="gravity", value=61.2,
                         computed_at=datetime(2026, 7, 16, 2, 10), inputs_hash="x" * 64,
                         components={}),
            ]
        )
        _s.commit()

from lens.api.app import app  # noqa: E402


def get(path: str, **kwargs) -> httpx.Response:
    async def _go() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path, **kwargs)

    return asyncio.run(_go())


# ------------------------------------------------------------------ tests


def test_health() -> None:
    body = get("/v1/health").json()
    assert body["data"] == {"status": "ok", "db": True, "olap": True}


def test_tenants_list() -> None:
    resp = get("/v1/tenants")
    assert resp.status_code == 200
    row = resp.json()["data"][0]
    assert row["slug"] == "meadow"
    assert row["shopify_domain"] == "meadow-botanicals.myshopify.com"
    assert row["plan"] == "advisory" and row["status"] == "active"


def test_overview_by_id_and_slug() -> None:
    for ref in ("1", "meadow"):
        resp = get(f"/v1/tenants/{ref}/overview")
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["total_revenue_paise"] == 184500000
        assert isinstance(data["total_revenue_paise"], int)  # paise stay ints
        assert data["scores"]["gravity"] == 61.2


def test_unknown_tenant_404_with_both_error_shapes() -> None:
    resp = get("/v1/tenants/999/overview")
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"] == "tenant not found"
    assert body["error"] == {"code": "not_found", "message": "tenant not found"}


def test_scores_latest() -> None:
    data = get("/v1/tenants/1/scores").json()["data"]
    assert data["definition_version"] == "v0.1"
    by_name = {s["score"]: s for s in data["scores"]}
    assert by_name["gravity"]["status"] == "computed"
    assert by_name["watertight"]["components"]["leak_total_paise"] == 9400000
    assert isinstance(by_name["watertight"]["components"]["leak_total_paise"], int)
    assert by_name["vitals"] == {"score": "vitals", "value": None, "status": "phase_2", "components": {}}


def test_score_history_and_unknown_score_404() -> None:
    data = get("/v1/tenants/1/scores/gravity/history").json()["data"]
    assert data == HISTORY
    # CONTRACTS V2.7: history accepts all nine + ciq + ciq_partial
    assert get("/v1/tenants/1/scores/vitals/history").status_code == 200
    assert get("/v1/tenants/1/scores/ciq/history").status_code == 200
    assert get("/v1/tenants/1/scores/nonsense/history").status_code == 404


def test_predictions_endpoint_and_pagination() -> None:
    resp = get("/v1/tenants/1/predictions", params={"page": 2, "page_size": 25})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert PRED_CALLS["predictions_summary"] == (1, 2, 25)
    assert data["band_counts"] == {"high": 812, "medium": 2404, "low": 5784}
    assert isinstance(data["at_risk_ltv_paise"], int)
    assert data["top_risk"][0]["churn_band"] == "high"


def test_experiments_endpoint() -> None:
    data = get("/v1/tenants/1/experiments").json()["data"]
    assert data == EXPERIMENTS


def test_cx_endpoint() -> None:
    data = get("/v1/tenants/1/cx").json()["data"]
    assert data == CX


def test_messaging_endpoint() -> None:
    data = get("/v1/tenants/1/messaging").json()["data"]
    assert data["whatsapp_summary"]["revenue_per_conversation_paise"] == 5413
    assert data["months"][0]["channel"] == "whatsapp"


def test_cohorts() -> None:
    data = get("/v1/tenants/1/cohorts").json()["data"]
    assert data["cohorts"][0]["cohort_month"] == "2025-01"
    assert data["cohorts"][0]["cells"][1]["retention_rate"] == 0.189


def test_rfm() -> None:
    data = get("/v1/tenants/1/rfm").json()["data"]
    assert data["segments"][0]["segment"] == "champions"
    assert data["grid"][0] == {"r_quintile": 5, "f_quintile": 5, "customers": 210, "revenue_paise": 18900000}


def test_revenue() -> None:
    data = get("/v1/tenants/1/revenue").json()["data"]
    assert data == REVENUE


def test_leaks() -> None:
    data = get("/v1/tenants/1/leaks").json()["data"]
    assert data["total_paise"] == 9400000
    assert {l["leak_type"] for l in data["leaks"]} <= {
        "preventable_churn", "rto_cod", "failed_payments", "discount_abuse",
    }


def test_customers_pagination() -> None:
    resp = get("/v1/tenants/1/customers", params={"segment": "loyal", "page": 3, "page_size": 25})
    assert resp.status_code == 200
    body = resp.json()
    assert CALLS["customers_page"] == (1, "loyal", 3, 25)
    assert body["page"] == 3 and body["page_size"] == 25 and body["total"] == 9840
    assert "name" not in body["data"][0] and "email" not in body["data"][0]  # no PII in lists


def test_customers_page_size_capped_at_200() -> None:
    resp = get("/v1/tenants/1/customers", params={"page_size": 500})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "validation_error"


def test_customer_detail_and_404() -> None:
    data = get("/v1/tenants/1/customers/4211").json()["data"]
    assert data["name"] == "Ananya Iyer" and data["phone"] == "+919876543210"
    assert data["orders"][0]["total_paise"] == 145000
    resp = get("/v1/tenants/1/customers/999999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "customer not found"


def test_meta_freshness() -> None:
    data = get("/v1/tenants/meadow/meta").json()["data"]
    assert data["tenant_id"] == 1
    assert {s["source"]: s["last_synced_at"] for s in data["syncs"]} == {
        "klaviyo": "2026-07-16T02:05:00Z",
        "shopify": "2026-07-16T02:00:00Z",
    }
    assert data["last_score_run_at"] == "2026-07-16T02:10:00Z"
    assert data["definition_version"] == "v0.1"


def test_cors_allows_dashboard_origin_only() -> None:
    ok = get("/v1/health", headers={"Origin": "http://127.0.0.1:3010"})
    assert ok.headers.get("access-control-allow-origin") == "http://127.0.0.1:3010"
    other = get("/v1/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in other.headers
