"""Interakt (WhatsApp BSP) raw -> core mappers.

Raw shapes the seeder lands (CONTRACTS.md V2.1):

interakt/campaigns::

    id, name, campaign_type (campaign|flow), channel="whatsapp", started_at

interakt/messages — one record per message per recipient::

    id, campaign_id, profile: {id, phone, email}, channel="whatsapp",
    sent_at, delivered_at, read_at, clicked_at, failed_at

    Mapping into lens.models.Message (one funnel vocabulary across channels):
    read_at -> opened_at · clicked_at (reply/click) -> clicked_at ·
    failed_at -> bounced_at. profile linking mirrors klaviyo._profile_customer
    (phone-first for WhatsApp; identity_type "interakt_profile_id" fallback).

interakt/consent — message-level opt-in/STOP ledger::

    id, profile, channel="whatsapp", action (granted|revoked),
    method (whatsapp_optin|stop_reply), occurred_at

Profile linking, per-batch prefetch maps and consent-flag recomputation are
REUSED from the klaviyo module (same semantics, ``source`` parametrized) —
one implementation of the merge-pointer-following identity code, not two.
Consent runs before messages so profile identities exist (RESOURCES order).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Campaign, ConsentLedger, Message
from .base import parse_dt
from .klaviyo import _apply_consent_flags, _Maps, _profile_customer, _profile_id

RESOURCES: tuple[str, ...] = ("campaigns", "consent", "messages")
RESOURCE_SOURCE: dict[str, str] = {r: "interakt" for r in RESOURCES}

SOURCE = "interakt"
PROFILE_IDENTITY = "interakt_profile_id"


def external_id(resource: str, payload: dict) -> str:
    return str(payload["id"])


def upsert(session: Session, tenant_id: int, resource: str, payloads: list[dict]) -> int:
    if not payloads:
        return 0
    fn = {"campaigns": _campaigns, "consent": _consent, "messages": _messages}[resource]
    return fn(session, tenant_id, payloads, _Maps(session, tenant_id, source=SOURCE))


def finalize(session: Session, tenant_id: int) -> None:
    return None  # consent flags are recomputed inside _consent


def _customer(session: Session, tenant_id: int, payload: dict, m: _Maps):
    return _profile_customer(
        session, tenant_id, payload, m, source=SOURCE, profile_identity=PROFILE_IDENTITY
    )


# ------------------------------------------------------------------------- campaigns


def _campaigns(session: Session, tenant_id: int, payloads: list[dict], m: _Maps) -> int:
    for payload in payloads:
        values = {
            "name": payload.get("name", ""),
            "campaign_type": payload.get("campaign_type") or payload.get("type", "campaign"),
            "channel": payload.get("channel", "whatsapp"),
            "subject": payload.get("subject"),
            "started_at": parse_dt(payload.get("started_at") or payload.get("created_at_utc")),
            "ended_at": parse_dt(payload.get("ended_at")),
        }
        ext = str(payload["id"])
        row = m.campaigns.get(ext)
        if row is None:
            row = Campaign(tenant_id=tenant_id, source=SOURCE, external_id=ext, **values)
            session.add(row)
            m.campaigns[ext] = row
        else:
            for key, val in values.items():
                setattr(row, key, val)
    session.flush()
    return len(payloads)


# --------------------------------------------------------------------------- consent


def _consent(session: Session, tenant_id: int, payloads: list[dict], m: _Maps) -> int:
    existing = set(
        session.scalars(
            select(ConsentLedger.external_id).where(
                ConsentLedger.tenant_id == tenant_id, ConsentLedger.source == SOURCE
            )
        )
    )
    touched: set[int] = set()
    for payload in payloads:
        customer = _customer(session, tenant_id, payload, m)
        touched.add(customer.id)
        ext = str(payload["id"])
        if ext in existing:
            continue  # ledger is append-only; re-sync must not duplicate
        session.add(
            ConsentLedger(
                tenant_id=tenant_id,
                customer_id=customer.id,
                channel=payload.get("channel", "whatsapp"),
                action=payload.get("action", "granted"),
                method=payload.get("method"),
                source=SOURCE,
                external_id=ext,
                occurred_at=parse_dt(payload.get("occurred_at")),
            )
        )
        existing.add(ext)
    session.flush()
    # cross-source last-action-wins: recompute reads the WHOLE ledger per customer
    _apply_consent_flags(session, tenant_id, touched, m)
    return len(payloads)


# -------------------------------------------------------------------------- messages


def _messages(session: Session, tenant_id: int, payloads: list[dict], m: _Maps) -> int:
    for payload in payloads:
        campaign = None
        if payload.get("campaign_id") is not None:
            campaign = m.campaigns.get(str(payload["campaign_id"]))
        customer_id = None
        profile_id = _profile_id(payload)
        if profile_id is not None:
            customer_id = m.ident.get((PROFILE_IDENTITY, profile_id))
        if customer_id is None:  # profile unseen by consent: full precedence lookup
            customer_id = _customer(session, tenant_id, payload, m).id
        values = {
            "campaign_id": campaign.id if campaign else None,
            "customer_id": customer_id,
            "channel": payload.get("channel", "whatsapp"),
            "sent_at": parse_dt(payload.get("sent_at")),
            "delivered_at": parse_dt(payload.get("delivered_at")),
            # WhatsApp read -> opened_at, reply/click -> clicked_at,
            # send failure -> bounced_at (CONTRACTS.md V2.0/V2.1)
            "opened_at": parse_dt(payload.get("read_at") or payload.get("opened_at")),
            "clicked_at": parse_dt(payload.get("clicked_at")),
            "bounced_at": parse_dt(payload.get("failed_at") or payload.get("bounced_at")),
            "unsubscribed_at": None,  # WhatsApp opt-outs arrive as consent revokes
        }
        ext = str(payload["id"])
        row = m.messages.get(ext)
        if row is None:
            row = Message(tenant_id=tenant_id, source=SOURCE, external_id=ext, **values)
            session.add(row)
            m.messages[ext] = row
        else:
            for key, val in values.items():
                setattr(row, key, val)
    session.flush()
    return len(payloads)
