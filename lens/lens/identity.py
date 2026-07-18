"""Deterministic phone-first identity resolution (blueprint 08 section 6, v0).

Union-find over exact match keys, precedence: shopify_customer_id > phone
(E.164-normalized, Indian 10-digit / 91-prefix / trunk-0 collapsed) >
lowercased trimmed email. Nodes are key strings; each customer's keys form one
component (from customer_identities plus the survivorship copies in
customer_pii), and a guest order's contact keys — read from its raw_records
payload, the only place guest PII lives — bridge components.

Components holding 2+ customers merge into the oldest customer (earliest
first_order_at, then earliest created_at, then lowest id). A merge writes an
identity_edges audit row, repoints customer_identities/orders/refunds/
messages/consent_ledger, fills PII gaps on the survivor, ORs opt-in flags, and
sets merged_into_customer_id on the absorbed row — nothing is ever deleted.
Guest orders attach to their component's survivor. Re-running is a no-op.

No probabilistic matching in v0. ponytail: guest orders whose contacts match
no known customer stay unresolved (counted in ResolveReport); the upgrade
path is a manually-reviewed fuzzy pass if the unresolved rate hurts Signal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .connectors.base import recompute_customer_stats
from .models import (
    ConsentLedger,
    Customer,
    CustomerIdentity,
    CustomerPII,
    IdentityEdge,
    Message,
    Order,
    RawRecord,
    Refund,
)

_PRECEDENCE = ("shopify_customer_id", "phone", "email")


def normalize_phone(raw: str | None) -> str | None:
    """E.164 with the Indian variants collapsed; None when not a usable phone.

    Handles: bare 10-digit mobiles (6-9 prefix), trunk-0 / 0091 prefixes,
    91-prefixed 12-digit forms, punctuation/whitespace. Non-Indian numbers
    pass through only when explicitly ``+``-prefixed.
    """
    if not raw:
        return None
    text = str(raw).strip()
    digits = re.sub(r"\D", "", text).lstrip("0")
    if len(digits) == 10 and digits[0] in "6789":
        return "+91" + digits
    if len(digits) == 12 and digits.startswith("91") and digits[2] in "6789":
        return "+" + digits
    if text.startswith("+") and 8 <= len(digits) <= 15:
        return "+" + digits
    return None


def normalize_email(raw: str | None) -> str | None:
    if not raw:
        return None
    text = str(raw).strip().lower()
    if "@" not in text or " " in text or "." not in text.rsplit("@", 1)[-1]:
        return None
    return text


@dataclass(frozen=True)
class ResolveReport:
    tenant_id: int
    customers_before: int
    customers_after: int
    merges: int
    orders_attached: int  # guest orders that gained a customer_id
    unresolved_orders: int  # still customer_id IS NULL
    match_rate: float  # share of orders with a customer_id (feeds Signal)


def resolve(session: Session, tenant_id: int) -> ResolveReport:
    live: dict[int, Customer] = {
        c.id: c
        for c in session.scalars(
            select(Customer).where(
                Customer.tenant_id == tenant_id, Customer.merged_into_customer_id.is_(None)
            )
        )
    }
    customers_before = len(live)

    # ---- gather match keys per customer (identities + PII survivorship copies)
    keys_by_customer: dict[int, set[str]] = {cid: set() for cid in live}
    owners_by_key: dict[str, set[int]] = {}

    def add_key(customer_id: int, itype: str, value: str | None) -> None:
        if not value:
            return
        key = f"{itype}:{value}"
        keys_by_customer[customer_id].add(key)
        owners_by_key.setdefault(key, set()).add(customer_id)

    for ident in session.scalars(
        select(CustomerIdentity).where(CustomerIdentity.tenant_id == tenant_id)
    ):
        if ident.customer_id in live and ident.identity_type in _PRECEDENCE:
            value = ident.identity_value
            if ident.identity_type == "phone":
                value = normalize_phone(value)
            elif ident.identity_type == "email":
                value = normalize_email(value)
            add_key(ident.customer_id, ident.identity_type, value)
    for pii in session.scalars(select(CustomerPII).where(CustomerPII.tenant_id == tenant_id)):
        if pii.customer_id in live:
            add_key(pii.customer_id, "phone", normalize_phone(pii.primary_phone))
            add_key(pii.customer_id, "email", normalize_email(pii.primary_email))

    # ---- union-find over key strings
    parent: dict[str, str] = {}

    def find(key: str) -> str:
        parent.setdefault(key, key)
        while parent[key] != key:
            parent[key] = parent[parent[key]]  # path halving
            key = parent[key]
        return key

    def union(a: str, b: str) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    for keys in keys_by_customer.values():
        ordered = sorted(keys)
        for a, b in zip(ordered, ordered[1:]):
            union(a, b)

    # ---- guest orders: contact keys from raw payloads bridge components
    guest_orders = session.scalars(
        select(Order).where(Order.tenant_id == tenant_id, Order.customer_id.is_(None))
    ).all()
    guest_keys: dict[int, list[str]] = {}
    for order in guest_orders:
        raw = session.scalars(
            select(RawRecord).filter_by(
                tenant_id=tenant_id,
                source=order.source,
                resource="orders",
                external_id=order.external_id,
            )
        ).first()
        payload = raw.payload if raw else {}
        phone = normalize_phone(
            payload.get("phone")
            or (payload.get("shipping_address") or {}).get("phone")
            or (payload.get("billing_address") or {}).get("phone")
        )
        email = normalize_email(payload.get("email") or payload.get("contact_email"))
        keys = [k for k in (f"phone:{phone}" if phone else None, f"email:{email}" if email else None) if k]
        guest_keys[order.id] = keys  # phone first = phone precedence on attach
        for a, b in zip(keys, keys[1:]):
            union(a, b)

    # ---- components -> merges
    components: dict[str, set[int]] = {}
    for key, owners in owners_by_key.items():
        components.setdefault(find(key), set()).update(owners)

    def age_key(customer_id: int) -> tuple:
        customer = live[customer_id]
        return (
            customer.first_order_at is None,
            customer.first_order_at or datetime.max,
            customer.created_at,
            customer_id,
        )

    merges = 0
    survivor_by_root: dict[str, int] = {}
    for root, customer_ids in components.items():
        ordered_ids = sorted(customer_ids, key=age_key)
        survivor_by_root[root] = ordered_ids[0]
        for absorbed_id in ordered_ids[1:]:
            _merge(session, tenant_id, live[ordered_ids[0]], live[absorbed_id], keys_by_customer)
            merges += 1

    # ---- attach guest orders to their component's survivor
    orders_attached = 0
    for order in guest_orders:
        for key in guest_keys[order.id]:
            survivor_id = survivor_by_root.get(find(key))
            if survivor_id is not None:
                order.customer_id = survivor_id
                orders_attached += 1
                break

    recompute_customer_stats(session, tenant_id)
    total_orders = (
        session.scalar(select(func.count()).select_from(Order).where(Order.tenant_id == tenant_id))
        or 0
    )
    unresolved = (
        session.scalar(
            select(func.count())
            .select_from(Order)
            .where(Order.tenant_id == tenant_id, Order.customer_id.is_(None))
        )
        or 0
    )
    session.commit()
    return ResolveReport(
        tenant_id=tenant_id,
        customers_before=customers_before,
        customers_after=customers_before - merges,
        merges=merges,
        orders_attached=orders_attached,
        unresolved_orders=unresolved,
        match_rate=1.0 if total_orders == 0 else 1 - unresolved / total_orders,
    )


def _merge(
    session: Session,
    tenant_id: int,
    survivor: Customer,
    absorbed: Customer,
    keys_by_customer: dict[int, set[str]],
) -> None:
    shared_types = {k.split(":", 1)[0] for k in keys_by_customer[survivor.id] & keys_by_customer[absorbed.id]}
    # transitive links (bridged via a guest order's contact pair) fall back to
    # the phone spine — the only way distinct key sets co-occur in v0
    merge_key = next((t for t in _PRECEDENCE if t in shared_types), "phone")
    session.add(
        IdentityEdge(
            tenant_id=tenant_id,
            survivor_id=survivor.id,
            absorbed_id=absorbed.id,
            merge_key=merge_key,
        )
    )
    for model in (CustomerIdentity, Order, Refund, Message, ConsentLedger):
        session.execute(
            update(model)
            .where(model.tenant_id == tenant_id, model.customer_id == absorbed.id)
            .values(customer_id=survivor.id)
        )
    absorbed_pii = session.get(CustomerPII, absorbed.id)
    if absorbed_pii is not None:
        survivor_pii = session.get(CustomerPII, survivor.id)
        if survivor_pii is None:
            survivor_pii = CustomerPII(customer_id=survivor.id, tenant_id=tenant_id)
            session.add(survivor_pii)
        for field in ("primary_email", "primary_phone", "first_name", "last_name"):
            # ponytail: fill-gaps survivorship (survivor's own values win); full
            # most-recent-non-null needs per-attribute timestamps we don't keep in v0
            if getattr(survivor_pii, field) is None and getattr(absorbed_pii, field) is not None:
                setattr(survivor_pii, field, getattr(absorbed_pii, field))
    survivor.accepts_email_marketing = survivor.accepts_email_marketing or absorbed.accepts_email_marketing
    survivor.whatsapp_opted_in = survivor.whatsapp_opted_in or absorbed.whatsapp_opted_in
    survivor.sms_opted_in = survivor.sms_opted_in or absorbed.sms_opted_in
    absorbed.merged_into_customer_id = survivor.id
    keys_by_customer[survivor.id] |= keys_by_customer[absorbed.id]
    session.flush()
