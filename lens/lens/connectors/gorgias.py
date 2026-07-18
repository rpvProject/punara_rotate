"""Gorgias (helpdesk) raw -> core mappers.

Raw shape the seeder lands (CONTRACTS.md V2.1):

gorgias/tickets::

    id, order_external_id, customer: {external_id} | null (guest),
    email, phone, channel (email|whatsapp|chat|instagram|phone),
    subject, category (delivery_delay|damaged|refund_where|quality|other),
    status (open|pending|resolved|closed),
    opened_at, first_response_at, resolved_at, csat (1-5 | null)

Maps to lens.models.SupportTicket. Order via (tenant, source='shopify',
external_id=order_external_id); customer via the klaviyo-style identity
precedence (shopify external_id > phone > email), following merge pointers,
leaving customer_id NULL when unresolved — voice-of-customer sources never
mint customers.

``_Maps.find_customer`` is the shared read-only lookup; judgeme imports it.
"""

from __future__ import annotations

from functools import cached_property

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..identity import normalize_email, normalize_phone
from ..models import Customer, CustomerIdentity, Order, Product, SupportTicket
from .base import parse_dt

RESOURCES: tuple[str, ...] = ("tickets",)
RESOURCE_SOURCE: dict[str, str] = {r: "gorgias" for r in RESOURCES}


def external_id(resource: str, payload: dict) -> str:
    return str(payload["id"])


class _Maps:
    """Lazy per-batch prefetch + read-only customer lookup (gorgias/judgeme)."""

    def __init__(self, session: Session, tenant_id: int) -> None:
        self._session = session
        self._tid = tenant_id

    @cached_property
    def ident(self) -> dict[tuple[str, str], int]:
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
    def orders(self) -> dict[str, int]:
        """shopify order external_id -> core order id."""
        return dict(
            self._session.execute(
                select(Order.external_id, Order.id).where(
                    Order.tenant_id == self._tid, Order.source == "shopify"
                )
            ).all()
        )

    @cached_property
    def products(self) -> dict[str, int]:  # used by judgeme only (lazy)
        return dict(
            self._session.execute(
                select(Product.external_id, Product.id).where(
                    Product.tenant_id == self._tid, Product.source == "shopify"
                )
            ).all()
        )

    def find_customer(
        self, shopify_external_id: str | None, phone: str | None, email: str | None
    ) -> int | None:
        """Identity precedence lookup; follows merge pointers; None if unresolved."""
        for itype, value in (
            ("shopify_customer_id", shopify_external_id),
            ("phone", normalize_phone(phone)),
            ("email", normalize_email(email)),
        ):
            if not value:
                continue
            customer_id = self.ident.get((itype, str(value)))
            if customer_id is None:
                continue
            customer = self.customers_by_id[customer_id]
            while customer.merged_into_customer_id is not None:  # follow merge pointers
                customer = self.customers_by_id[customer.merged_into_customer_id]
            return customer.id
        return None

    def order_id(self, payload: dict) -> int | None:
        ext = payload.get("order_external_id")
        return self.orders.get(str(ext)) if ext is not None else None


def upsert(session: Session, tenant_id: int, resource: str, payloads: list[dict]) -> int:
    if not payloads:
        return 0
    m = _Maps(session, tenant_id)
    existing = {
        t.external_id: t
        for t in session.scalars(
            select(SupportTicket).filter_by(tenant_id=tenant_id, source="gorgias")
        )
    }
    for payload in payloads:
        embedded = payload.get("customer") or {}
        values = {
            "customer_id": m.find_customer(
                embedded.get("external_id"), payload.get("phone"), payload.get("email")
            ),
            "order_id": m.order_id(payload),
            "channel": payload.get("channel", "email"),
            "subject": payload.get("subject"),
            "category": payload.get("category"),
            "status": payload.get("status", "open"),
            "opened_at": parse_dt(payload.get("opened_at") or payload.get("created_datetime")),
            "first_response_at": parse_dt(payload.get("first_response_at")),
            "resolved_at": parse_dt(payload.get("resolved_at") or payload.get("closed_datetime")),
            "csat": payload.get("csat"),
        }
        ext = str(payload["id"])
        row = existing.get(ext)
        if row is None:
            row = SupportTicket(tenant_id=tenant_id, source="gorgias", external_id=ext, **values)
            session.add(row)
            existing[ext] = row
        else:
            for key, val in values.items():
                setattr(row, key, val)
    session.flush()
    return len(payloads)


def finalize(session: Session, tenant_id: int) -> None:
    return None
