"""Klaviyo raw -> core mappers: campaigns, consent-from-profiles, messages.

Payload subsets consumed (v0 FLATTENED shapes — the live Klaviyo API is
JSON:API-shaped and splits engagement into /events; the reshaping layer for
live payloads is Phase 2, see synthetic.HttpKlaviyoTransport):

klaviyo/campaigns::

    id, name, campaign_type|type (campaign|flow), channel (email|sms), subject,
    started_at|send_time, ended_at|end_time

klaviyo/consent — one record per (profile, channel) grant/revoke action::

    id, profile: {id, email, phone}  (seeded shape, CONTRACTS section 2.1)
        or flattened profile_id/email/phone_number,
    external_id (shopify customer id, when Klaviyo knows it),
    channel (email|whatsapp|sms), action (granted|revoked), method, occurred_at

klaviyo/messages — one record per message per recipient, engagement flattened
to timestamps (delivery-states-as-timestamps per 11_data_model.md)::

    id, campaign_id, profile (or profile_id), channel (email|sms), sent_at,
    delivered_at, opened_at, clicked_at, bounced_at, unsubscribed_at

Profile -> customer linking precedence (deterministic): shopify external_id >
phone E.164 > email > klaviyo_profile_id, else a new ``source="klaviyo"``
customer is created and identity.resolve() merges it later if evidence appears.
Consent resource runs before messages so profile identities exist.

Mappers prefetch existing rows into per-batch maps (see ``_Maps``) so a sync
issues a handful of bulk SELECTs instead of one per record.
"""

from __future__ import annotations

from functools import cached_property

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..identity import normalize_email, normalize_phone
from ..models import Campaign, ConsentLedger, Customer, CustomerIdentity, CustomerPII, Message
from .base import parse_dt

RESOURCES: tuple[str, ...] = ("campaigns", "consent", "messages")
RESOURCE_SOURCE: dict[str, str] = {r: "klaviyo" for r in RESOURCES}

_FLAG_BY_CHANNEL = {
    "email": "accepts_email_marketing",
    "whatsapp": "whatsapp_opted_in",
    "sms": "sms_opted_in",
}


def external_id(resource: str, payload: dict) -> str:
    return str(payload["id"])


class _Maps:
    """Lazy per-batch prefetch (same pattern as shopify._Maps).

    ``source`` parametrizes the campaign/message prefetch so the interakt
    connector (identical profile-linking semantics) reuses this class.
    """

    def __init__(self, session: Session, tenant_id: int, source: str = "klaviyo") -> None:
        self._session = session
        self._tid = tenant_id
        self._source = source

    @cached_property
    def campaigns(self) -> dict[str, Campaign]:
        return {
            c.external_id: c
            for c in self._session.scalars(
                select(Campaign).filter_by(tenant_id=self._tid, source=self._source)
            )
        }

    @cached_property
    def messages(self) -> dict[str, Message]:
        return {
            m.external_id: m
            for m in self._session.scalars(
                select(Message).filter_by(tenant_id=self._tid, source=self._source)
            )
        }

    @cached_property
    def ident(self) -> dict[tuple[str, str], int]:
        """(identity_type, identity_value) -> customer_id, whole tenant."""
        return {
            (i.identity_type, i.identity_value): i.customer_id
            for i in self._session.scalars(
                select(CustomerIdentity).where(CustomerIdentity.tenant_id == self._tid)
            )
        }

    @cached_property
    def customers_by_id(self) -> dict[int, Customer]:
        return {
            c.id: c
            for c in self._session.scalars(
                select(Customer).where(Customer.tenant_id == self._tid)
            )
        }

    @cached_property
    def pii(self) -> dict[int, CustomerPII]:
        return {
            p.customer_id: p
            for p in self._session.scalars(
                select(CustomerPII).where(CustomerPII.tenant_id == self._tid)
            )
        }


def upsert(session: Session, tenant_id: int, resource: str, payloads: list[dict]) -> int:
    if not payloads:
        return 0
    fn = {"campaigns": _campaigns, "consent": _consent, "messages": _messages}[resource]
    return fn(session, tenant_id, payloads, _Maps(session, tenant_id))


def finalize(session: Session, tenant_id: int) -> None:
    return None  # consent flags are recomputed inside _consent


# ------------------------------------------------------------------------- campaigns


def _campaigns(session: Session, tenant_id: int, payloads: list[dict], m: _Maps) -> int:
    for payload in payloads:
        values = {
            "name": payload.get("name", ""),
            "campaign_type": payload.get("campaign_type") or payload.get("type", "campaign"),
            "channel": payload.get("channel", "email"),
            "subject": payload.get("subject"),
            "started_at": parse_dt(payload.get("started_at") or payload.get("send_time")),
            "ended_at": parse_dt(payload.get("ended_at") or payload.get("end_time")),
        }
        ext = str(payload["id"])
        row = m.campaigns.get(ext)
        if row is None:
            row = Campaign(tenant_id=tenant_id, source="klaviyo", external_id=ext, **values)
            session.add(row)
            m.campaigns[ext] = row
        else:
            for key, val in values.items():
                setattr(row, key, val)
    session.flush()
    return len(payloads)


# -------------------------------------------------------------------------- profiles


def _profile_id(payload: dict) -> str | None:
    """Flattened `profile_id` or the seeder's nested `profile: {id, ...}` block."""
    profile = payload.get("profile") or {}
    value = profile.get("id") or payload.get("profile_id")
    return None if value is None else str(value)


def _profile_customer(
    session: Session,
    tenant_id: int,
    payload: dict,
    m: _Maps,
    source: str = "klaviyo",
    profile_identity: str = "klaviyo_profile_id",
) -> Customer:
    """Deterministic get-or-create for a messaging profile (klaviyo/interakt)."""
    profile = payload.get("profile") or {}
    phone = normalize_phone(profile.get("phone") or payload.get("phone_number"))
    email = normalize_email(profile.get("email") or payload.get("email"))
    profile_id = _profile_id(payload) or str(payload["id"])

    customer: Customer | None = None
    for itype, value in (
        ("shopify_customer_id", payload.get("external_id")),
        ("phone", phone),
        ("email", email),
        (profile_identity, profile_id),
    ):
        if not value:
            continue
        customer_id = m.ident.get((itype, str(value)))
        if customer_id is not None:
            customer = m.customers_by_id[customer_id]
            break
    if customer is None:
        customer = Customer(tenant_id=tenant_id, source=source, external_id=profile_id)
        created = parse_dt(payload.get("occurred_at") or payload.get("sent_at"))
        if created is not None:
            customer.created_at = created
        session.add(customer)
        session.flush()  # id needed for identities/PII
        m.customers_by_id[customer.id] = customer
    while customer.merged_into_customer_id is not None:  # follow merge pointers
        customer = m.customers_by_id[customer.merged_into_customer_id]

    for itype, value in (
        (profile_identity, profile_id),
        ("phone", phone),
        ("email", email),
    ):
        if not value:
            continue
        key = (itype, str(value))
        if key not in m.ident:  # claimed values stay put: that's the merge signal
            session.add(
                CustomerIdentity(
                    tenant_id=tenant_id,
                    customer_id=customer.id,
                    identity_type=itype,
                    identity_value=str(value),
                    source=source,
                )
            )
            m.ident[key] = customer.id
    if phone or email:
        pii = m.pii.get(customer.id)
        if pii is None:
            pii = CustomerPII(customer_id=customer.id, tenant_id=tenant_id)
            session.add(pii)
            m.pii[customer.id] = pii
        # survivorship priority Shopify > messaging: klaviyo only fills gaps
        if email and pii.primary_email is None:
            pii.primary_email = email
        if phone and pii.primary_phone is None:
            pii.primary_phone = phone
    return customer


# --------------------------------------------------------------------------- consent


def _consent(session: Session, tenant_id: int, payloads: list[dict], m: _Maps) -> int:
    existing = set(
        session.scalars(
            select(ConsentLedger.external_id).where(
                ConsentLedger.tenant_id == tenant_id, ConsentLedger.source == "klaviyo"
            )
        )
    )
    touched: set[int] = set()
    for payload in payloads:
        customer = _profile_customer(session, tenant_id, payload, m)
        touched.add(customer.id)
        ext = str(payload["id"])
        if ext in existing:
            continue  # ledger is append-only; re-sync must not duplicate
        session.add(
            ConsentLedger(
                tenant_id=tenant_id,
                customer_id=customer.id,
                channel=payload.get("channel", "email"),
                action=payload.get("action", "granted"),
                method=payload.get("method"),
                source="klaviyo",
                external_id=ext,
                occurred_at=parse_dt(payload.get("occurred_at")),
            )
        )
        existing.add(ext)
    session.flush()
    _apply_consent_flags(session, tenant_id, touched, m)
    return len(payloads)


def _apply_consent_flags(
    session: Session, tenant_id: int, customer_ids: set[int], m: _Maps
) -> None:
    """Current opt-in state = last ledger action per (customer, channel)."""
    if not customer_ids:
        return
    rows = session.execute(
        select(ConsentLedger.customer_id, ConsentLedger.channel, ConsentLedger.action)
        .where(ConsentLedger.tenant_id == tenant_id, ConsentLedger.customer_id.in_(customer_ids))
        .order_by(ConsentLedger.occurred_at, ConsentLedger.id)
    ).all()
    last: dict[tuple[int, str], str] = {}
    for customer_id, channel, action in rows:
        last[(customer_id, channel)] = action
    for (customer_id, channel), action in last.items():
        flag = _FLAG_BY_CHANNEL.get(channel)
        if flag is None:
            continue
        customer = m.customers_by_id.get(customer_id) or session.get(Customer, customer_id)
        setattr(customer, flag, action == "granted")


# -------------------------------------------------------------------------- messages


def _messages(session: Session, tenant_id: int, payloads: list[dict], m: _Maps) -> int:
    for payload in payloads:
        campaign = None
        if payload.get("campaign_id") is not None:
            campaign = m.campaigns.get(str(payload["campaign_id"]))
        customer_id = None
        profile_id = _profile_id(payload)
        if profile_id is not None:
            customer_id = m.ident.get(("klaviyo_profile_id", profile_id))
            if customer_id is None:  # profile unseen by consent: full precedence lookup
                customer_id = _profile_customer(session, tenant_id, payload, m).id
        values = {
            "campaign_id": campaign.id if campaign else None,
            "customer_id": customer_id,
            "channel": payload.get("channel", "email"),
            "sent_at": parse_dt(payload.get("sent_at")),
            "delivered_at": parse_dt(payload.get("delivered_at")),
            "opened_at": parse_dt(payload.get("opened_at")),
            "clicked_at": parse_dt(payload.get("clicked_at")),
            "bounced_at": parse_dt(payload.get("bounced_at")),
            "unsubscribed_at": parse_dt(payload.get("unsubscribed_at")),
        }
        ext = str(payload["id"])
        row = m.messages.get(ext)
        if row is None:
            row = Message(tenant_id=tenant_id, source="klaviyo", external_id=ext, **values)
            session.add(row)
            m.messages[ext] = row
        else:
            for key, val in values.items():
                setattr(row, key, val)
    session.flush()
    return len(payloads)
