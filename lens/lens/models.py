"""Punara Lens v0 core schema (SQLite via SQLAlchemy 2.0).

Follows blueprint/11_data_model.md, adapted per docs/ADR-001-v0-storage.md:
- All money is integer paise. Floats never touch revenue.
- Every tenant-scoped table carries tenant_id; every query must filter by it.
- Idempotent ingestion: UNIQUE (tenant_id, source, external_id) on sourced tables.
- PII lives ONLY in customer_pii; nothing in the OLAP export may join to it.
- Allowed values for status-like columns are documented inline and in
  lens/CONTRACTS.md; enforced by writers, not CHECK constraints, in v0.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------- tenancy


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    shopify_domain: Mapped[str | None]
    base_currency: Mapped[str] = mapped_column(default="INR")
    plan: Mapped[str] = mapped_column(default="advisory")  # launch|grow|scale|enterprise|advisory
    country: Mapped[str] = mapped_column(default="IN")
    status: Mapped[str] = mapped_column(default="active")  # active|paused|churned
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# --------------------------------------------------------------------------- identity


class Customer(Base):
    """Pseudonymous core customer. PII lives only in customer_pii."""

    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source", "external_id"),
        Index("ix_customers_tenant_stage", "tenant_id", "lifecycle_stage"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    source: Mapped[str]  # shopify|klaviyo|punara
    external_id: Mapped[str]
    first_order_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_order_at: Mapped[datetime | None] = mapped_column(DateTime)
    orders_count: Mapped[int] = mapped_column(default=0)
    total_spent_paise: Mapped[int] = mapped_column(default=0)
    lifecycle_stage: Mapped[str] = mapped_column(default="new")  # new|active|loyal|slipping|dormant|lost
    accepts_email_marketing: Mapped[bool] = mapped_column(default=False)
    whatsapp_opted_in: Mapped[bool] = mapped_column(default=False)
    sms_opted_in: Mapped[bool] = mapped_column(default=False)
    merged_into_customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CustomerPII(Base):
    """The ONLY table holding names/emails/phones. Never exported to DuckDB."""

    __tablename__ = "customer_pii"
    __table_args__ = (
        Index("ix_pii_tenant_phone", "tenant_id", "primary_phone"),
        Index("ix_pii_tenant_email", "tenant_id", "primary_email"),
    )

    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    primary_email: Mapped[str | None]  # lowercased, trimmed
    primary_phone: Mapped[str | None]  # E.164
    first_name: Mapped[str | None]
    last_name: Mapped[str | None]
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CustomerIdentity(Base):
    """Every known handle -> one customer. Deterministic resolution only in v0."""

    __tablename__ = "customer_identities"
    __table_args__ = (
        UniqueConstraint("tenant_id", "identity_type", "identity_value"),
        Index("ix_identities_tenant_customer", "tenant_id", "customer_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    identity_type: Mapped[str]  # shopify_customer_id|phone|email|klaviyo_profile_id
    identity_value: Mapped[str]  # normalized: E.164 phone, lowercase email
    source: Mapped[str]
    confidence: Mapped[str] = mapped_column(default="deterministic")  # deterministic|manual
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class IdentityEdge(Base):
    """Merge audit trail: absorbed -> survivor, explainable and reversible."""

    __tablename__ = "identity_edges"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    survivor_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    absorbed_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    merge_key: Mapped[str]  # shopify_customer_id|phone|email|manual
    merged_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# --------------------------------------------------------------------------- catalog


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("tenant_id", "source", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    source: Mapped[str]
    external_id: Mapped[str]
    title: Mapped[str]
    product_type: Mapped[str | None]
    vendor: Mapped[str | None]
    status: Mapped[str] = mapped_column(default="active")  # active|draft|archived
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Variant(Base):
    __tablename__ = "variants"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source", "external_id"),
        Index("ix_variants_tenant_sku", "tenant_id", "sku"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    source: Mapped[str]
    external_id: Mapped[str]
    sku: Mapped[str | None]
    title: Mapped[str | None]
    price_paise: Mapped[int] = mapped_column(default=0)
    compare_at_price_paise: Mapped[int | None]
    cost_paise: Mapped[int | None]
    currency: Mapped[str] = mapped_column(default="INR")


# --------------------------------------------------------------------------- order graph


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source", "external_id"),
        Index("ix_orders_tenant_customer_placed", "tenant_id", "customer_id", "placed_at"),
        Index("ix_orders_tenant_placed", "tenant_id", "placed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))  # NULL = guest, pending resolution
    source: Mapped[str]
    external_id: Mapped[str]
    order_number: Mapped[str | None]
    placed_at: Mapped[datetime] = mapped_column(DateTime)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime)
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)
    financial_status: Mapped[str] = mapped_column(default="pending")
    # pending|authorized|paid|partially_refunded|refunded|voided
    fulfillment_status: Mapped[str] = mapped_column(default="unfulfilled")
    # unfulfilled|partial|fulfilled|delivered|rto
    cod: Mapped[bool] = mapped_column(default=False)  # first-class: COD drives RTO and Watertight
    payment_gateway: Mapped[str | None]  # razorpay|shopify_payments|...
    subtotal_paise: Mapped[int] = mapped_column(default=0)
    discount_paise: Mapped[int] = mapped_column(default=0)
    shipping_paise: Mapped[int] = mapped_column(default=0)
    tax_paise: Mapped[int] = mapped_column(default=0)
    total_paise: Mapped[int] = mapped_column(default=0)
    currency: Mapped[str] = mapped_column(default="INR")
    discount_codes: Mapped[str | None]  # comma-separated snapshot
    customer_order_index: Mapped[int | None]  # 1 = first order, 2 = the second order


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        Index("ix_order_items_tenant_order", "tenant_id", "order_id"),
        Index("ix_order_items_tenant_product", "tenant_id", "product_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("variants.id"))
    sku: Mapped[str | None]  # snapshot at purchase
    title: Mapped[str | None]
    quantity: Mapped[int] = mapped_column(default=1)
    unit_price_paise: Mapped[int] = mapped_column(default=0)
    discount_paise: Mapped[int] = mapped_column(default=0)
    unit_cost_paise: Mapped[int | None]


class Refund(Base):
    __tablename__ = "refunds"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source", "external_id"),
        Index("ix_refunds_tenant_order", "tenant_id", "order_id"),
        Index("ix_refunds_tenant_type", "tenant_id", "refund_type", "processed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    source: Mapped[str]
    external_id: Mapped[str]
    amount_paise: Mapped[int]
    currency: Mapped[str] = mapped_column(default="INR")
    refund_type: Mapped[str] = mapped_column(default="return")  # return|rto|goodwill|payment_failure
    processed_at: Mapped[datetime] = mapped_column(DateTime)
    gateway: Mapped[str | None]


class Shipment(Base):
    __tablename__ = "shipments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source", "external_id"),
        Index("ix_shipments_tenant_order", "tenant_id", "order_id"),
        Index("ix_shipments_tenant_rto", "tenant_id", "rto"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    source: Mapped[str]  # shiprocket
    external_id: Mapped[str]
    courier: Mapped[str | None]
    status: Mapped[str] = mapped_column(default="pending")
    # pending|in_transit|delivered|rto_initiated|rto_received|lost
    rto: Mapped[bool] = mapped_column(default=False)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)
    rto_at: Mapped[datetime | None] = mapped_column(DateTime)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source", "external_id"),
        Index("ix_payments_tenant_order", "tenant_id", "order_id"),
        Index("ix_payments_tenant_status", "tenant_id", "status", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    source: Mapped[str]  # razorpay
    external_id: Mapped[str]
    method: Mapped[str]  # upi|card|netbanking|wallet|cod
    gateway: Mapped[str | None]
    status: Mapped[str]  # created|authorized|captured|failed|refunded
    amount_paise: Mapped[int]
    currency: Mapped[str] = mapped_column(default="INR")
    failure_reason: Mapped[str | None]
    occurred_at: Mapped[datetime] = mapped_column(DateTime)


# --------------------------------------------------------------------------- messaging


class Campaign(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source", "external_id"),
        Index("ix_campaigns_tenant_channel", "tenant_id", "channel", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    source: Mapped[str]  # klaviyo|interakt
    external_id: Mapped[str]
    name: Mapped[str]
    campaign_type: Mapped[str] = mapped_column(default="campaign")  # campaign|flow
    channel: Mapped[str] = mapped_column(default="email")  # email|sms|whatsapp
    subject: Mapped[str | None]
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)


class Message(Base):
    """One row per message per recipient. Delivery states as timestamps (relaxation per 11_data_model.md)."""

    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source", "external_id"),
        Index("ix_messages_tenant_customer_sent", "tenant_id", "customer_id", "sent_at"),
        Index("ix_messages_tenant_campaign", "tenant_id", "campaign_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id"))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    channel: Mapped[str] = mapped_column(default="email")  # email|sms|whatsapp
    source: Mapped[str]
    external_id: Mapped[str]
    sent_at: Mapped[datetime] = mapped_column(DateTime)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime)  # email open / whatsapp read
    clicked_at: Mapped[datetime | None] = mapped_column(DateTime)  # first click / whatsapp reply
    bounced_at: Mapped[datetime | None] = mapped_column(DateTime)  # bounce / whatsapp send failure
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime)


class ConsentLedger(Base):
    """Append-only. Current opt-in state on customers is derived from this."""

    __tablename__ = "consent_ledger"
    __table_args__ = (
        Index("ix_consent_tenant_customer", "tenant_id", "customer_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    channel: Mapped[str]  # email|whatsapp|sms
    action: Mapped[str]  # granted|revoked
    method: Mapped[str | None]  # checkout|form|import|unsubscribe_link
    source: Mapped[str]
    external_id: Mapped[str | None]
    occurred_at: Mapped[datetime] = mapped_column(DateTime)


# --------------------------------------------------------------------------- voice of customer (Phase 2)


class SupportTicket(Base):
    """Support tickets (gorgias source). Feeds the Pulse score + cx_facts mart."""

    __tablename__ = "support_tickets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source", "external_id"),
        Index("ix_tickets_tenant_status", "tenant_id", "status", "opened_at"),
        Index("ix_tickets_tenant_customer", "tenant_id", "customer_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    source: Mapped[str]  # gorgias
    external_id: Mapped[str]
    channel: Mapped[str] = mapped_column(default="email")  # email|whatsapp|instagram|phone|chat
    subject: Mapped[str | None]
    category: Mapped[str | None]  # delivery_delay|damaged|refund_where|quality|other
    status: Mapped[str] = mapped_column(default="open")  # open|pending|resolved|closed
    opened_at: Mapped[datetime] = mapped_column(DateTime)
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    csat: Mapped[int | None]  # 1-5, on a subset of resolved tickets


class Review(Base):
    """Product reviews (judgeme source). Feeds Pulse review-sentiment component."""

    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source", "external_id"),
        Index("ix_reviews_tenant_product", "tenant_id", "product_id", "submitted_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    source: Mapped[str]  # judgeme
    external_id: Mapped[str]
    rating: Mapped[int]  # 1-5
    title: Mapped[str | None]
    body: Mapped[str | None] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(default=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime)


class NpsResponse(Base):
    """NPS survey responses. Seeded direct to core (source='punara').

    ``customer_external_id`` (the pseudonymous shopify customer external id) is
    the linking key at seed time — customers do not exist in core until sync
    runs. ``seed.link_direct()`` fills ``customer_id`` in the nightly pipeline
    after identity resolution.
    """

    __tablename__ = "nps_responses"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source", "external_id"),
        Index("ix_nps_tenant_responded", "tenant_id", "responded_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    customer_external_id: Mapped[str | None]  # shopify external id, pseudonymous
    source: Mapped[str] = mapped_column(default="punara")
    external_id: Mapped[str]
    score: Mapped[int]  # 0-10
    comment: Mapped[str | None] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(default="post_purchase_widget")
    # email|whatsapp|post_purchase_widget
    responded_at: Mapped[datetime] = mapped_column(DateTime)


# --------------------------------------------------------------------------- experimentation (Phase 2)


class Experiment(Base):
    """Loop Ledger entries — the Velocity score's system of record.

    v0-of-phase-2 flattening of 11_data_model.md's experiments/variants/results
    tables: one row per experiment with the readout inline. Variant/exposure
    grain arrives when Lens actually runs assignments.
    """

    __tablename__ = "experiments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name"),
        Index("ix_experiments_tenant_status", "tenant_id", "status", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    name: Mapped[str]
    hypothesis: Mapped[str] = mapped_column(Text)
    score_target: Mapped[str]  # which of the nine scores it moves: gravity|flow|...
    status: Mapped[str] = mapped_column(default="draft")  # draft|running|concluded
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    concluded_at: Mapped[datetime | None] = mapped_column(DateTime)
    sample_size: Mapped[int | None]
    lift_pct: Mapped[float | None]  # primary-metric lift, e.g. 8.5 = +8.5%
    significant: Mapped[bool | None]
    decision: Mapped[str | None]  # shipped|killed|inconclusive
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# --------------------------------------------------------------------------- ml predictions (Phase 2)


class Prediction(Base):
    """Nightly batch ML output (BG/NBD + Gamma-Gamma + churn bands).

    One row per (tenant, customer, model_version, scored_on-date): re-running
    the nightly on the same day replaces that day's row (upsert); a new day
    appends, so model drift stays measurable (11_data_model.md: predictions
    are never silently overwritten across days).
    """

    __tablename__ = "predictions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "customer_id", "model_version", "scored_on"),
        Index("ix_predictions_tenant_band", "tenant_id", "churn_band"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    p_alive: Mapped[float]  # BG/NBD P(alive), 0-1
    expected_orders_90d: Mapped[float]
    ltv_12m_paise: Mapped[int]
    churn_band: Mapped[str]  # high|medium|low
    model_version: Mapped[str]
    scored_at: Mapped[datetime] = mapped_column(DateTime)
    scored_on: Mapped[date] = mapped_column(Date)  # date(scored_at); nightly upsert key


# --------------------------------------------------------------------------- pipeline plumbing


class SyncState(Base):
    """Per (tenant, source, resource) sync cursor; re-running sync is a no-op."""

    __tablename__ = "sync_state"
    __table_args__ = (UniqueConstraint("tenant_id", "source", "resource"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    source: Mapped[str]
    resource: Mapped[str]
    cursor: Mapped[str | None]
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime)


class RawRecord(Base):
    """Landing zone: every inbound payload verbatim before interpretation."""

    __tablename__ = "raw_records"
    __table_args__ = (UniqueConstraint("tenant_id", "source", "resource", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    source: Mapped[str]  # shopify|razorpay|shiprocket|klaviyo|interakt|gorgias|judgeme
    resource: Mapped[str]  # orders|customers|payments|shipments|campaigns|messages|consent|tickets|reviews
    external_id: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSON)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EventDefinition(Base):
    """Persisted mirror of lens.events.EVENTS (the code is the source of truth)."""

    __tablename__ = "event_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_name: Mapped[str] = mapped_column(unique=True)
    category: Mapped[str]  # commerce|payment|logistics|messaging|voice|experiment
    description: Mapped[str | None] = mapped_column(Text)
    required_properties: Mapped[dict] = mapped_column(JSON)
    is_derived: Mapped[bool] = mapped_column(default=False)


class ScoreRun(Base):
    """Every score computation, append-only. Reproducibility is the brand promise."""

    __tablename__ = "score_runs"
    __table_args__ = (
        Index("ix_score_runs_tenant_score", "tenant_id", "score", "computed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"))
    score: Mapped[str]  # gravity|flow|signal|watertight|ciq_partial (Phase 2: the rest)
    value: Mapped[float]  # 0-100
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    definition_version: Mapped[str] = mapped_column(default="v0.1")
    inputs_hash: Mapped[str]  # sha256 of the mart inputs the score read
    components: Mapped[dict] = mapped_column(JSON)  # sub-score decomposition
