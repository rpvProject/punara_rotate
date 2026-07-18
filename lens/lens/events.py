"""Canonical event dictionary — v0 subset of blueprint/11_data_model.md's 30 events.

Closed vocabulary: an event not in EVENTS is rejected at export, never stored.
Naming: object_action, snake_case, past tense.

Envelope on every event (not repeated in required_properties):
    tenant_id, customer_id (nullable), occurred_at, source, external_id
event_id = sha256(f"{tenant_id}|{source}|{external_id}|{event_name}") hex digest.

v0 subset rationale: only events the synthetic seeder can generate from the
Shopify/Razorpay/Shiprocket/Klaviyo transports AND that Gravity/Flow/Signal/
Watertight consume. Skipped: pixel/engagement events (no pixel),
cart_abandoned, cod_confirmed (no GoKwik), loyalty/subscription events
(no supporting tables in the schema).

Phase 2 additions: voice events (ticket_opened, ticket_resolved,
review_submitted, nps_submitted) and experiment_concluded. WhatsApp
(interakt) deliberately REUSES the message_* events with
``properties.channel == "whatsapp"`` — a WhatsApp "read" is message_opened,
a reply/click is message_clicked, a send failure is message_bounced. One
funnel vocabulary across channels keeps every messaging mart channel-generic.
"""

import hashlib
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class EventDef:
    name: str
    category: str  # commerce|payment|logistics|messaging|voice|experiment
    description: str
    required_properties: Mapping[str, str]  # property -> type name
    sources: tuple[str, ...]
    is_derived: bool = field(default=False)


def _e(
    name: str,
    category: str,
    description: str,
    props: dict[str, str],
    sources: tuple[str, ...],
    is_derived: bool = False,
) -> tuple[str, EventDef]:
    return name, EventDef(name, category, description, MappingProxyType(props), sources, is_derived)


EVENTS: Mapping[str, EventDef] = MappingProxyType(
    dict(
        [
            # ---- commerce
            _e(
                "customer_created",
                "commerce",
                "A customer record appeared in the source system.",
                {"source_customer_id": "str", "accepts_marketing": "bool"},
                ("shopify",),
            ),
            _e(
                "order_placed",
                "commerce",
                "An order was placed.",
                {
                    "order_id": "int",
                    "total_paise": "int",
                    "currency": "str",
                    "cod": "bool",
                    "discount_paise": "int",
                    "customer_order_index": "int",
                },
                ("shopify",),
            ),
            _e(
                "order_cancelled",
                "commerce",
                "An order was cancelled before fulfilment.",
                {"order_id": "int", "reason": "str"},
                ("shopify",),
            ),
            # ---- logistics
            _e(
                "order_fulfilled",
                "logistics",
                "An order was handed to a courier.",
                {"order_id": "int", "courier": "str"},
                ("shopify", "shiprocket"),
            ),
            _e(
                "order_delivered",
                "logistics",
                "An order reached the customer.",
                {"order_id": "int", "days_in_transit": "int"},
                ("shiprocket",),
            ),
            _e(
                "order_rto",
                "logistics",
                "An order returned to origin (RTO).",
                {"order_id": "int", "cod": "bool", "courier": "str"},
                ("shiprocket",),
            ),
            # ---- payment
            _e(
                "payment_captured",
                "payment",
                "A payment was captured.",
                {"order_id": "int", "amount_paise": "int", "gateway": "str", "method": "str"},
                ("razorpay",),
            ),
            _e(
                "payment_failed",
                "payment",
                "A payment attempt failed.",
                {"order_id": "int", "amount_paise": "int", "failure_reason": "str"},
                ("razorpay",),
            ),
            _e(
                "order_refunded",
                "payment",
                "A refund was issued against an order.",
                {"refund_id": "int", "order_id": "int", "amount_paise": "int", "refund_type": "str"},
                ("shopify", "razorpay"),
            ),
            # ---- messaging
            _e(
                "message_sent",
                "messaging",
                "A message was sent to a recipient.",
                {"message_id": "int", "campaign_id": "int", "channel": "str"},
                ("klaviyo", "interakt"),
            ),
            _e(
                "message_delivered",
                "messaging",
                "A message reached the recipient's inbox/device.",
                {"message_id": "int", "channel": "str"},
                ("klaviyo", "interakt"),
            ),
            _e(
                "message_opened",
                "messaging",
                "A message was opened (email) or read (WhatsApp).",
                {"message_id": "int", "channel": "str"},
                ("klaviyo", "interakt"),
            ),
            _e(
                "message_clicked",
                "messaging",
                "A link in a message was clicked (or a WhatsApp reply).",
                {"message_id": "int", "channel": "str"},
                ("klaviyo", "interakt"),
            ),
            _e(
                "message_bounced",
                "messaging",
                "A message bounced or a WhatsApp send failed.",
                {"message_id": "int", "channel": "str"},
                ("klaviyo", "interakt"),
            ),
            _e(
                "channel_opted_in",
                "messaging",
                "Consent granted on a channel.",
                {"channel": "str", "method": "str"},
                ("shopify", "klaviyo", "interakt"),
            ),
            _e(
                "channel_opted_out",
                "messaging",
                "Consent revoked on a channel.",
                {"channel": "str", "reason": "str"},
                ("klaviyo", "interakt"),
            ),
            # ---- voice (Phase 2)
            _e(
                "ticket_opened",
                "voice",
                "A support ticket was opened.",
                {"ticket_id": "int", "channel": "str", "category": "str"},
                ("gorgias",),
            ),
            _e(
                "ticket_resolved",
                "voice",
                "A support ticket was resolved.",
                {"ticket_id": "int", "hours_to_resolve": "float", "csat_score": "int"},
                ("gorgias",),
            ),
            _e(
                "review_submitted",
                "voice",
                "A product review was submitted.",
                {"review_id": "int", "product_id": "int", "rating": "int"},
                ("judgeme",),
            ),
            _e(
                "nps_submitted",
                "voice",
                "An NPS survey response was submitted.",
                {"nps_response_id": "int", "score": "int", "channel": "str"},
                ("punara",),
            ),
            # ---- experiment (Phase 2)
            _e(
                "experiment_concluded",
                "experiment",
                "A Loop Ledger experiment was concluded and decided.",
                {"experiment_id": "int", "score_target": "str", "decision": "str", "lift_pct": "float"},
                ("punara",),
                is_derived=True,
            ),
        ]
    )
)


def event_id(tenant_id: int, source: str, external_id: str, event_name: str) -> str:
    """Deterministic event id — idempotent export, dedup key in DuckDB."""
    return hashlib.sha256(f"{tenant_id}|{source}|{external_id}|{event_name}".encode()).hexdigest()


if __name__ == "__main__":  # smallest check that fails if the dictionary breaks
    assert len(EVENTS) == 21, len(EVENTS)
    assert all(k == v.name for k, v in EVENTS.items())
    assert event_id(1, "shopify", "ord_1", "order_placed") == event_id(1, "shopify", "ord_1", "order_placed")
    assert event_id(1, "shopify", "ord_1", "order_placed") != event_id(2, "shopify", "ord_1", "order_placed")
    print("events.py self-check OK")
