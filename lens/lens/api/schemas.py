"""Pydantic v2 response models mirroring CONTRACTS.md §3 verbatim.

Paise are ints and stay ints — the API never converts to rupees.
Timestamps are ISO-8601 UTC strings ("2026-07-01T00:00:00Z"), months "YYYY-MM".
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    data: T


# --------------------------------------------------------------------- tenants


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    shopify_domain: str | None
    base_currency: str
    plan: str
    status: str


# -------------------------------------------------------------------- overview


class Overview(BaseModel):
    as_of: str | None  # None until the tenant's first pipeline run
    window_months: int
    total_revenue_paise: int
    repeat_revenue_paise: int
    repeat_rate: float
    orders: int
    customers: int
    new_customers_last_month: int
    aov_paise: int
    leak_total_paise: int
    scores: dict[str, float | None]


# ---------------------------------------------------------------------- scores


class ScoreItem(BaseModel):
    score: str
    value: float | None
    status: str  # computed|phase_2
    # verbatim engine components: sub-scores (float), *_raw (may be None),
    # *_note (str), paise (int), plus ciq's coverage/phase_2 nested values
    components: dict[str, Any]


class ScoresLatest(BaseModel):
    computed_at: str | None
    definition_version: str | None
    scores: list[ScoreItem]


class ScoreHistoryPoint(BaseModel):
    computed_at: str
    value: float
    definition_version: str


# --------------------------------------------------------------------- cohorts


class CohortCell(BaseModel):
    months_since: int
    active_customers: int
    retention_rate: float
    repeat_revenue_paise: int


class CohortRow(BaseModel):
    cohort_month: str  # "YYYY-MM"
    cohort_size: int
    cells: list[CohortCell]


class Cohorts(BaseModel):
    cohorts: list[CohortRow]


# ------------------------------------------------------------------------- rfm


class RfmSegment(BaseModel):
    segment: str
    customers: int
    revenue_paise: int
    avg_recency_days: int
    avg_frequency: float
    avg_monetary_paise: int


class RfmGridCell(BaseModel):
    r_quintile: int
    f_quintile: int
    customers: int
    revenue_paise: int


class Rfm(BaseModel):
    as_of: str | None  # None until the tenant's first pipeline run
    segments: list[RfmSegment]
    grid: list[RfmGridCell]


# --------------------------------------------------------------------- revenue


class RevenueMonth(BaseModel):
    month: str
    revenue_paise: int
    repeat_revenue_paise: int
    orders: int
    new_customers: int
    returning_customers: int
    repeat_rate: float
    aov_paise: int


# ------------------------------------------------------------------- campaigns


class CampaignRoiRow(BaseModel):
    """campaign_roi mart row, served verbatim (CONTRACTS §3 /campaigns)."""

    campaign_id: int
    campaign_name: str
    channel: str
    campaign_type: str
    sends: int
    delivered: int
    unique_opens: int
    unique_clicks: int
    unsubscribes: int
    bounces: int
    attributed_orders: int
    attributed_revenue_paise: int
    revenue_per_message_paise: int


# ----------------------------------------------------------------------- leaks


class LeakLine(BaseModel):
    leak_type: str  # preventable_churn|rto_cod|failed_payments|discount_abuse
    amount_paise: int
    orders_affected: int
    revenue_share: float


class LeakMonthly(BaseModel):
    month: str
    leak_type: str
    amount_paise: int


class Leaks(BaseModel):
    window_months: int
    total_paise: int
    annualized_paise: int
    revenue_share: float
    leaks: list[LeakLine]
    monthly: list[LeakMonthly]


# ------------------------------------------------------------------- customers


class CustomerListItem(BaseModel):
    """Pseudonymous — never carries PII."""

    id: int
    lifecycle_stage: str
    rfm_segment: str | None
    orders_count: int
    total_spent_paise: int
    first_order_at: str | None
    last_order_at: str | None
    recency_days: int | None
    whatsapp_opted_in: bool


class CustomersPage(BaseModel):
    data: list[CustomerListItem]
    page: int
    page_size: int
    total: int


class IdentityOut(BaseModel):
    identity_type: str
    identity_value: str


class CustomerOrderOut(BaseModel):
    id: int
    order_number: str | None
    placed_at: str
    total_paise: int
    cod: bool
    financial_status: str
    fulfillment_status: str


class PredictionOut(BaseModel):
    """CONTRACTS V2.7 customer_detail `prediction` block."""

    p_alive: float
    expected_orders_90d: float
    ltv_12m_paise: int
    churn_band: str  # high|medium|low
    model_version: str
    scored_at: str


class CustomerTicketOut(BaseModel):
    id: int
    subject: str | None
    category: str | None
    status: str
    opened_at: str
    resolved_at: str | None
    csat: int | None


class CustomerReviewOut(BaseModel):
    id: int
    rating: int
    title: str | None
    verified: bool
    submitted_at: str


class CustomerNpsOut(BaseModel):
    id: int
    score: int
    responded_at: str


class CustomerDetail(BaseModel):
    """The ONLY response shape carrying PII (joined from SQLite)."""

    id: int
    name: str | None
    email: str | None
    phone: str | None
    lifecycle_stage: str
    rfm_segment: str | None
    orders_count: int
    total_spent_paise: int
    first_order_at: str | None
    last_order_at: str | None
    consent: dict[str, bool]
    identities: list[IdentityOut]
    orders: list[CustomerOrderOut]
    # Phase 2 additions (defaults keep pre-v2 payloads valid)
    prediction: PredictionOut | None = None
    tickets: list[CustomerTicketOut] = []
    reviews: list[CustomerReviewOut] = []
    nps: list[CustomerNpsOut] = []


# -------------------------------------------------------------- health / meta


class Health(BaseModel):
    status: str  # ok|degraded
    db: bool
    olap: bool


class SourceFreshness(BaseModel):
    source: str
    last_synced_at: str | None


class Meta(BaseModel):
    """Data freshness — stale data is a client-facing fact (08 §11)."""

    tenant_id: int
    syncs: list[SourceFreshness]
    last_score_run_at: str | None
    definition_version: str | None
