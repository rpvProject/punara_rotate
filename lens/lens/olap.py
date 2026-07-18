"""DuckDB OLAP layer: connection + core -> canonical events + pseudonymous dims/facts.

PII never crosses this boundary: customer_pii is not read here, dim_customers
carries only pseudonymous columns, and merged customer rows are skipped.

ponytail: export is full-replace per tenant (DELETE + INSERT). At v0 scale a
rebuild is the honest choice; upgrade path is incremental upserts keyed on
event_id / (tenant_id, *_id) when row counts make rebuilds hurt.
"""

from __future__ import annotations

import json
from datetime import datetime

import duckdb
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .config import settings
from .events import event_id

# Every table (core mirrors + marts) is created here with IF NOT EXISTS so
# queries against a fresh file return empty shapes instead of erroring.
_DDL: list[str] = [
    """CREATE TABLE IF NOT EXISTS events (
        event_id VARCHAR NOT NULL, tenant_id BIGINT NOT NULL,
        event_name VARCHAR NOT NULL, customer_id BIGINT, order_id BIGINT,
        message_id BIGINT, occurred_at TIMESTAMP NOT NULL,
        source VARCHAR NOT NULL, external_id VARCHAR NOT NULL,
        amount_paise BIGINT, properties JSON)""",
    """CREATE TABLE IF NOT EXISTS dim_customers (
        tenant_id BIGINT NOT NULL, customer_id BIGINT NOT NULL,
        lifecycle_stage VARCHAR, first_order_at TIMESTAMP, last_order_at TIMESTAMP,
        orders_count INTEGER, total_spent_paise BIGINT,
        accepts_email_marketing BOOLEAN, whatsapp_opted_in BOOLEAN,
        sms_opted_in BOOLEAN, created_at TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS dim_products (
        tenant_id BIGINT NOT NULL, product_id BIGINT NOT NULL,
        title VARCHAR, product_type VARCHAR, vendor VARCHAR, status VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS dim_variants (
        tenant_id BIGINT NOT NULL, variant_id BIGINT NOT NULL, product_id BIGINT,
        sku VARCHAR, price_paise BIGINT, cost_paise BIGINT)""",
    """CREATE TABLE IF NOT EXISTS fact_orders (
        tenant_id BIGINT NOT NULL, order_id BIGINT NOT NULL, customer_id BIGINT,
        placed_at TIMESTAMP, cancelled_at TIMESTAMP, fulfilled_at TIMESTAMP,
        delivered_at TIMESTAMP, financial_status VARCHAR, fulfillment_status VARCHAR,
        cod BOOLEAN, subtotal_paise BIGINT, discount_paise BIGINT,
        shipping_paise BIGINT, tax_paise BIGINT, total_paise BIGINT,
        customer_order_index INTEGER, discount_codes VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS fact_order_items (
        tenant_id BIGINT NOT NULL, order_item_id BIGINT NOT NULL, order_id BIGINT,
        product_id BIGINT, variant_id BIGINT, sku VARCHAR, quantity INTEGER,
        unit_price_paise BIGINT, discount_paise BIGINT, unit_cost_paise BIGINT)""",
    """CREATE TABLE IF NOT EXISTS fact_refunds (
        tenant_id BIGINT NOT NULL, refund_id BIGINT NOT NULL, order_id BIGINT,
        customer_id BIGINT, amount_paise BIGINT, refund_type VARCHAR,
        processed_at TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS fact_payments (
        tenant_id BIGINT NOT NULL, payment_id BIGINT NOT NULL, order_id BIGINT,
        method VARCHAR, status VARCHAR, amount_paise BIGINT,
        failure_reason VARCHAR, occurred_at TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS fact_shipments (
        tenant_id BIGINT NOT NULL, shipment_id BIGINT NOT NULL, order_id BIGINT,
        status VARCHAR, rto BOOLEAN, shipped_at TIMESTAMP,
        delivered_at TIMESTAMP, rto_at TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS dim_campaigns (
        tenant_id BIGINT NOT NULL, campaign_id BIGINT NOT NULL, name VARCHAR,
        campaign_type VARCHAR, channel VARCHAR, started_at TIMESTAMP,
        external_id VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS fact_messages (
        tenant_id BIGINT NOT NULL, message_id BIGINT NOT NULL, campaign_id BIGINT,
        customer_id BIGINT, channel VARCHAR, sent_at TIMESTAMP,
        delivered_at TIMESTAMP, opened_at TIMESTAMP, clicked_at TIMESTAMP,
        bounced_at TIMESTAMP, unsubscribed_at TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS fact_consent (
        tenant_id BIGINT NOT NULL, consent_id BIGINT NOT NULL, customer_id BIGINT,
        channel VARCHAR, action VARCHAR, occurred_at TIMESTAMP)""",
    # ---- Phase 2 facts (CONTRACTS V2.5 — pseudonymous, free text never exported)
    """CREATE TABLE IF NOT EXISTS fact_tickets (
        tenant_id BIGINT NOT NULL, ticket_id BIGINT NOT NULL, customer_id BIGINT,
        order_id BIGINT, channel VARCHAR, category VARCHAR, status VARCHAR,
        opened_at TIMESTAMP, first_response_at TIMESTAMP, resolved_at TIMESTAMP,
        csat INTEGER)""",
    """CREATE TABLE IF NOT EXISTS fact_reviews (
        tenant_id BIGINT NOT NULL, review_id BIGINT NOT NULL, customer_id BIGINT,
        order_id BIGINT, product_id BIGINT, rating INTEGER, verified BOOLEAN,
        submitted_at TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS fact_nps (
        tenant_id BIGINT NOT NULL, nps_id BIGINT NOT NULL, customer_id BIGINT,
        score INTEGER, channel VARCHAR, responded_at TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS fact_experiments (
        tenant_id BIGINT NOT NULL, experiment_id BIGINT NOT NULL, name VARCHAR,
        score_target VARCHAR, status VARCHAR, started_at TIMESTAMP,
        concluded_at TIMESTAMP, sample_size INTEGER, lift_pct DOUBLE,
        significant BOOLEAN, decision VARCHAR)""",
    # ---- marts (populated by marts.build)
    """CREATE TABLE IF NOT EXISTS rfm_current (
        tenant_id BIGINT, customer_id BIGINT, recency_days INTEGER,
        frequency INTEGER, monetary_paise BIGINT, r_quintile TINYINT,
        f_quintile TINYINT, m_quintile TINYINT, rfm_segment VARCHAR,
        lifecycle_stage VARCHAR, whatsapp_opted_in BOOLEAN, as_of DATE)""",
    """CREATE TABLE IF NOT EXISTS cohort_retention (
        tenant_id BIGINT, cohort_month DATE, months_since INTEGER,
        cohort_size INTEGER, active_customers INTEGER, retention_rate DOUBLE,
        repeat_revenue_paise BIGINT, avg_orders_per_active DOUBLE)""",
    """CREATE TABLE IF NOT EXISTS retention_facts (
        tenant_id BIGINT, customer_id BIGINT, month DATE,
        orders_in_month INTEGER, revenue_in_month_paise BIGINT,
        cumulative_orders INTEGER, cumulative_revenue_paise BIGINT,
        lifecycle_stage VARCHAR, days_since_last_order INTEGER, is_active BOOLEAN,
        rto_orders_in_month INTEGER, refund_paise_in_month BIGINT,
        acquisition_month DATE)""",
    """CREATE TABLE IF NOT EXISTS campaign_roi (
        tenant_id BIGINT, campaign_id BIGINT, campaign_name VARCHAR,
        channel VARCHAR, campaign_type VARCHAR, sends INTEGER, delivered INTEGER,
        unique_opens INTEGER, unique_clicks INTEGER, unsubscribes INTEGER,
        bounces INTEGER, attributed_orders INTEGER,
        attributed_revenue_paise BIGINT, revenue_per_message_paise BIGINT)""",
    """CREATE TABLE IF NOT EXISTS executive_kpis (
        tenant_id BIGINT, month DATE, total_revenue_paise BIGINT,
        repeat_revenue_paise BIGINT, repeat_rate DOUBLE, orders INTEGER,
        aov_paise BIGINT, new_customers INTEGER, returning_customers INTEGER,
        rto_loss_paise BIGINT, failed_payment_loss_paise BIGINT,
        refund_loss_paise BIGINT, discount_paise BIGINT, leak_total_paise BIGINT)""",
    """CREATE TABLE IF NOT EXISTS leak_facts (
        tenant_id BIGINT, month DATE, leak_type VARCHAR,
        amount_paise BIGINT, orders_affected INTEGER, revenue_share DOUBLE)""",
    # ---- Phase 2 marts (CONTRACTS V2.5)
    """CREATE TABLE IF NOT EXISTS cx_facts (
        tenant_id BIGINT, month DATE,
        orders_delivered INTEGER, median_delivery_days DOUBLE,
        rto_orders INTEGER, rto_rate DOUBLE,
        tickets_opened INTEGER, ticket_rate DOUBLE,
        median_resolution_hours DOUBLE, breach_rate DOUBLE, avg_csat DOUBLE,
        reviews INTEGER, avg_review_rating DOUBLE,
        nps_responses INTEGER, nps DOUBLE)""",
    """CREATE TABLE IF NOT EXISTS messaging_facts (
        tenant_id BIGINT, month DATE, channel VARCHAR,
        sends INTEGER, delivered INTEGER, opened_or_read INTEGER, clicked INTEGER,
        bounced INTEGER, bounce_rate DOUBLE, unsubscribed INTEGER,
        attributed_orders INTEGER, attributed_revenue_paise BIGINT,
        revenue_per_message_paise BIGINT)""",
    """CREATE TABLE IF NOT EXISTS automation_facts (
        tenant_id BIGINT, moment VARCHAR, covered BOOLEAN, campaign_id BIGINT,
        sends INTEGER, attributed_orders INTEGER, attributed_revenue_paise BIGINT,
        automated_revenue_share DOUBLE)""",
    """CREATE TABLE IF NOT EXISTS experiment_facts (
        tenant_id BIGINT, experiment_id BIGINT, name VARCHAR, score_target VARCHAR,
        status VARCHAR, decision VARCHAR,
        started_at TIMESTAMP, concluded_at TIMESTAMP, started_month DATE,
        sample_size INTEGER, lift_pct DOUBLE, significant BOOLEAN,
        days_to_decision INTEGER)""",
]


def get_conn() -> duckdb.DuckDBPyConnection:
    """Open settings.olap_path and ensure the full schema exists."""
    con = duckdb.connect(settings.olap_path)
    for ddl in _DDL:
        con.execute(ddl)
    # v2 migration: pre-v2 files lack the moment-mapping column (CONTRACTS V2.5
    # maps flow external ids KLF-01/02/03 to lifecycle moments).
    con.execute("ALTER TABLE dim_campaigns ADD COLUMN IF NOT EXISTS external_id VARCHAR")
    return con


def _replace(
    con: duckdb.DuckDBPyConnection,
    table: str,
    columns: tuple[str, ...],
    rows: list[tuple],
    tenant_id: int,
) -> None:
    con.execute(f"DELETE FROM {table} WHERE tenant_id = ?", [tenant_id])
    if rows:
        # bulk path: DuckDB executemany is row-at-a-time (minutes at 10^5 rows);
        # a registered DataFrame ingests in one vectorized scan. dtype=object
        # keeps ints/None exact — no NaN-in-BIGINT surprises.
        frame = pd.DataFrame(rows, columns=list(columns), dtype=object)
        con.register("_lens_batch", frame)
        cols = ", ".join(columns)
        con.execute(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM _lens_batch")
        con.unregister("_lens_batch")


def export_core(session: Session, tenant_id: int) -> None:
    """Full-replace this tenant's DuckDB events + dims/facts from the SQLite core."""
    tid = tenant_id

    def _all(model):  # noqa: ANN001 - internal helper
        return list(session.scalars(select(model).where(model.tenant_id == tid)))

    customers = [c for c in _all(models.Customer) if c.merged_into_customer_id is None]
    products = _all(models.Product)
    variants = _all(models.Variant)
    orders = _all(models.Order)
    items = _all(models.OrderItem)
    refunds = _all(models.Refund)
    payments = _all(models.Payment)
    shipments = _all(models.Shipment)
    campaigns = _all(models.Campaign)
    messages = _all(models.Message)
    consent = _all(models.ConsentLedger)
    tickets = _all(models.SupportTicket)
    reviews = _all(models.Review)
    nps = _all(models.NpsResponse)
    experiments = _all(models.Experiment)
    order_by_id = {o.id: o for o in orders}

    # ---- canonical events (dedup on event_id; closed vocabulary of lens.events)
    ev: dict[str, tuple] = {}

    def add(
        name: str,
        source: str,
        ext: str,
        occurred: datetime | None,
        customer_id: int | None = None,
        order_id: int | None = None,
        message_id: int | None = None,
        amount: int | None = None,
        props: dict | None = None,
    ) -> None:
        if occurred is None:
            return
        eid = event_id(tid, source, ext, name)
        ev[eid] = (eid, tid, name, customer_id, order_id, message_id,
                   occurred, source, ext, amount, json.dumps(props or {}))

    for c in customers:
        add("customer_created", c.source, c.external_id, c.created_at, customer_id=c.id,
            props={"source_customer_id": c.external_id,
                   "accepts_marketing": bool(c.accepts_email_marketing)})
    for o in orders:
        add("order_placed", o.source, o.external_id, o.placed_at, o.customer_id, o.id,
            amount=o.total_paise,
            props={"order_id": o.id, "total_paise": o.total_paise, "currency": o.currency,
                   "cod": bool(o.cod), "discount_paise": o.discount_paise,
                   "customer_order_index": o.customer_order_index})
        if o.cancelled_at:
            add("order_cancelled", o.source, o.external_id, o.cancelled_at,
                o.customer_id, o.id, props={"order_id": o.id, "reason": "unknown"})
    for s in shipments:
        o = order_by_id.get(s.order_id)
        cid = o.customer_id if o else None
        if s.shipped_at:
            add("order_fulfilled", s.source, s.external_id, s.shipped_at, cid, s.order_id,
                props={"order_id": s.order_id, "courier": s.courier or "unknown"})
        if s.delivered_at:
            days = (s.delivered_at - s.shipped_at).days if s.shipped_at else 0
            add("order_delivered", s.source, s.external_id, s.delivered_at, cid, s.order_id,
                props={"order_id": s.order_id, "days_in_transit": days})
        if s.rto:
            add("order_rto", s.source, s.external_id,
                s.rto_at or s.delivered_at or s.shipped_at, cid, s.order_id,
                amount=o.total_paise if o else None,
                props={"order_id": s.order_id, "cod": bool(o.cod) if o else False,
                       "courier": s.courier or "unknown"})
    for p in payments:
        o = order_by_id.get(p.order_id) if p.order_id else None
        cid = o.customer_id if o else None
        if p.status == "captured":
            add("payment_captured", p.source, p.external_id, p.occurred_at, cid,
                p.order_id, amount=p.amount_paise,
                props={"order_id": p.order_id, "amount_paise": p.amount_paise,
                       "gateway": p.gateway or "unknown", "method": p.method})
        elif p.status == "failed":
            add("payment_failed", p.source, p.external_id, p.occurred_at, cid,
                p.order_id, amount=p.amount_paise,
                props={"order_id": p.order_id, "amount_paise": p.amount_paise,
                       "failure_reason": p.failure_reason or "unknown"})
    for r in refunds:
        o = order_by_id.get(r.order_id)
        add("order_refunded", r.source, r.external_id, r.processed_at,
            r.customer_id or (o.customer_id if o else None), r.order_id,
            amount=r.amount_paise,
            props={"refund_id": r.id, "order_id": r.order_id,
                   "amount_paise": r.amount_paise, "refund_type": r.refund_type})
    for m in messages:
        base = {"message_id": m.id, "channel": m.channel}
        add("message_sent", m.source, m.external_id, m.sent_at, m.customer_id,
            message_id=m.id,
            props={"message_id": m.id, "campaign_id": m.campaign_id, "channel": m.channel})
        if m.delivered_at:
            add("message_delivered", m.source, m.external_id, m.delivered_at,
                m.customer_id, message_id=m.id, props=base)
        if m.opened_at:
            add("message_opened", m.source, m.external_id, m.opened_at,
                m.customer_id, message_id=m.id, props=base)
        if m.clicked_at:
            add("message_clicked", m.source, m.external_id, m.clicked_at,
                m.customer_id, message_id=m.id, props=base)
        if m.bounced_at:
            add("message_bounced", m.source, m.external_id, m.bounced_at,
                m.customer_id, message_id=m.id, props=base)
    for l in consent:  # noqa: E741
        ext = l.external_id or f"consent-{l.id}"
        if l.action == "granted":
            add("channel_opted_in", l.source, ext, l.occurred_at, l.customer_id,
                props={"channel": l.channel, "method": l.method or "unknown"})
        else:
            add("channel_opted_out", l.source, ext, l.occurred_at, l.customer_id,
                props={"channel": l.channel, "reason": l.method or "unsubscribe"})
    # ---- Phase 2 voice + experiment events (CONTRACTS V2.0/V2.5)
    for tk in tickets:
        add("ticket_opened", tk.source, tk.external_id, tk.opened_at,
            tk.customer_id, tk.order_id,
            props={"ticket_id": tk.id, "channel": tk.channel,
                   "category": tk.category or "other"})
        if tk.resolved_at:
            hours = (tk.resolved_at - tk.opened_at).total_seconds() / 3600.0
            add("ticket_resolved", tk.source, tk.external_id, tk.resolved_at,
                tk.customer_id, tk.order_id,
                props={"ticket_id": tk.id, "hours_to_resolve": hours,
                       "csat_score": tk.csat})
    for rv in reviews:
        add("review_submitted", rv.source, rv.external_id, rv.submitted_at,
            rv.customer_id, rv.order_id,
            props={"review_id": rv.id, "product_id": rv.product_id,
                   "rating": rv.rating})
    for n in nps:
        add("nps_submitted", n.source, n.external_id, n.responded_at, n.customer_id,
            props={"nps_response_id": n.id, "score": n.score, "channel": n.channel})
    for e in experiments:
        if e.status == "concluded" and e.concluded_at:
            # experiments key on (tenant_id, name) — the name IS the external id
            add("experiment_concluded", "punara", e.name, e.concluded_at,
                props={"experiment_id": e.id, "score_target": e.score_target,
                       "decision": e.decision or "undecided", "lift_pct": e.lift_pct})

    con = get_conn()
    try:
        _replace(con, "events",
                 ("event_id", "tenant_id", "event_name", "customer_id", "order_id",
                  "message_id", "occurred_at", "source", "external_id",
                  "amount_paise", "properties"),
                 list(ev.values()), tid)
        _replace(con, "dim_customers",
                 ("tenant_id", "customer_id", "lifecycle_stage", "first_order_at",
                  "last_order_at", "orders_count", "total_spent_paise",
                  "accepts_email_marketing", "whatsapp_opted_in", "sms_opted_in",
                  "created_at"),
                 [(tid, c.id, c.lifecycle_stage, c.first_order_at, c.last_order_at,
                   c.orders_count, c.total_spent_paise, bool(c.accepts_email_marketing),
                   bool(c.whatsapp_opted_in), bool(c.sms_opted_in), c.created_at)
                  for c in customers], tid)
        _replace(con, "dim_products",
                 ("tenant_id", "product_id", "title", "product_type", "vendor", "status"),
                 [(tid, p.id, p.title, p.product_type, p.vendor, p.status)
                  for p in products], tid)
        _replace(con, "dim_variants",
                 ("tenant_id", "variant_id", "product_id", "sku", "price_paise",
                  "cost_paise"),
                 [(tid, v.id, v.product_id, v.sku, v.price_paise, v.cost_paise)
                  for v in variants], tid)
        _replace(con, "fact_orders",
                 ("tenant_id", "order_id", "customer_id", "placed_at", "cancelled_at",
                  "fulfilled_at", "delivered_at", "financial_status",
                  "fulfillment_status", "cod", "subtotal_paise", "discount_paise",
                  "shipping_paise", "tax_paise", "total_paise",
                  "customer_order_index", "discount_codes"),
                 [(tid, o.id, o.customer_id, o.placed_at, o.cancelled_at, o.fulfilled_at,
                   o.delivered_at, o.financial_status, o.fulfillment_status, bool(o.cod),
                   o.subtotal_paise, o.discount_paise, o.shipping_paise, o.tax_paise,
                   o.total_paise, o.customer_order_index, o.discount_codes)
                  for o in orders], tid)
        _replace(con, "fact_order_items",
                 ("tenant_id", "order_item_id", "order_id", "product_id", "variant_id",
                  "sku", "quantity", "unit_price_paise", "discount_paise",
                  "unit_cost_paise"),
                 [(tid, i.id, i.order_id, i.product_id, i.variant_id, i.sku, i.quantity,
                   i.unit_price_paise, i.discount_paise, i.unit_cost_paise)
                  for i in items], tid)
        _replace(con, "fact_refunds",
                 ("tenant_id", "refund_id", "order_id", "customer_id", "amount_paise",
                  "refund_type", "processed_at"),
                 [(tid, r.id, r.order_id, r.customer_id, r.amount_paise, r.refund_type,
                   r.processed_at) for r in refunds], tid)
        _replace(con, "fact_payments",
                 ("tenant_id", "payment_id", "order_id", "method", "status",
                  "amount_paise", "failure_reason", "occurred_at"),
                 [(tid, p.id, p.order_id, p.method, p.status, p.amount_paise,
                   p.failure_reason, p.occurred_at) for p in payments], tid)
        _replace(con, "fact_shipments",
                 ("tenant_id", "shipment_id", "order_id", "status", "rto",
                  "shipped_at", "delivered_at", "rto_at"),
                 [(tid, s.id, s.order_id, s.status, bool(s.rto), s.shipped_at,
                   s.delivered_at, s.rto_at) for s in shipments], tid)
        _replace(con, "dim_campaigns",
                 ("tenant_id", "campaign_id", "name", "campaign_type", "channel",
                  "started_at", "external_id"),
                 [(tid, c.id, c.name, c.campaign_type, c.channel, c.started_at,
                   c.external_id) for c in campaigns], tid)
        _replace(con, "fact_messages",
                 ("tenant_id", "message_id", "campaign_id", "customer_id", "channel",
                  "sent_at", "delivered_at", "opened_at", "clicked_at", "bounced_at",
                  "unsubscribed_at"),
                 [(tid, m.id, m.campaign_id, m.customer_id, m.channel, m.sent_at,
                   m.delivered_at, m.opened_at, m.clicked_at, m.bounced_at,
                   m.unsubscribed_at) for m in messages], tid)
        _replace(con, "fact_consent",
                 ("tenant_id", "consent_id", "customer_id", "channel", "action",
                  "occurred_at"),
                 [(tid, l.id, l.customer_id, l.channel, l.action, l.occurred_at)
                  for l in consent], tid)
        # ---- Phase 2 facts: pseudonymous only — ticket subject, review
        # title/body and NPS comments deliberately stay in SQLite.
        _replace(con, "fact_tickets",
                 ("tenant_id", "ticket_id", "customer_id", "order_id", "channel",
                  "category", "status", "opened_at", "first_response_at",
                  "resolved_at", "csat"),
                 [(tid, tk.id, tk.customer_id, tk.order_id, tk.channel, tk.category,
                   tk.status, tk.opened_at, tk.first_response_at, tk.resolved_at,
                   tk.csat) for tk in tickets], tid)
        _replace(con, "fact_reviews",
                 ("tenant_id", "review_id", "customer_id", "order_id", "product_id",
                  "rating", "verified", "submitted_at"),
                 [(tid, rv.id, rv.customer_id, rv.order_id, rv.product_id, rv.rating,
                   bool(rv.verified), rv.submitted_at) for rv in reviews], tid)
        _replace(con, "fact_nps",
                 ("tenant_id", "nps_id", "customer_id", "score", "channel",
                  "responded_at"),
                 [(tid, n.id, n.customer_id, n.score, n.channel, n.responded_at)
                  for n in nps], tid)
        _replace(con, "fact_experiments",
                 ("tenant_id", "experiment_id", "name", "score_target", "status",
                  "started_at", "concluded_at", "sample_size", "lift_pct",
                  "significant", "decision"),
                 [(tid, e.id, e.name, e.score_target, e.status, e.started_at,
                   e.concluded_at, e.sample_size, e.lift_pct, e.significant,
                   e.decision) for e in experiments], tid)
    finally:
        con.close()
