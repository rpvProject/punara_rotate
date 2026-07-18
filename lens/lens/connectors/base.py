"""Connector framework: Transport -> raw_records -> typed core rows.

Per blueprint/08_technical_architecture.md section 3, adapted to v0 (ADR-001):

- Every inbound record lands verbatim in ``raw_records`` before interpretation
  (unique ``(tenant_id, source, resource, external_id)``, conflict = skip).
- Core upserts key on ``(tenant_id, source, external_id)`` so re-running any
  sync is a no-op: cursors advance past already-fetched pages, and a forced
  re-fetch overwrites rows with identical values.
- ``sync_state`` stores one cursor per (tenant, sync source, resource).

The Transport protocol is the seam where a real HTTP client slots in later:
the SyncRunner and the resource mappers never know whether pages come from
raw fixtures (synthetic.py) or a live API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..models import Customer, CustomerIdentity, Order, RawRecord, SyncState


class Transport(Protocol):
    """Pages records for one resource.

    ``fetch_page(resource, cursor)`` returns ``(records, next_cursor)``.
    An empty ``records`` list means end of stream (return the cursor you were
    given so the caller persists the resume point). ``next_cursor`` may be
    non-None on the final non-empty page; the caller stops on the next empty
    page and persists the last cursor it saw.
    """

    def fetch_page(self, resource: str, cursor: str | None) -> tuple[list[dict], str | None]: ...


@dataclass(frozen=True)
class SyncReport:
    tenant_id: int
    source: str  # shopify|klaviyo|interakt|gorgias|judgeme
    resources: dict[str, int]  # resource -> core rows upserted (primary rows)
    started_at: datetime
    finished_at: datetime
    fetched: int = 0  # records returned by the transport
    inserted_raw: int = 0  # new raw_records rows landed
    skipped: int = 0  # records already present in raw_records


class SyncRunner:
    """Walks a source's resources through a Transport, lands raw, upserts core."""

    def __init__(self, transport: Transport | None = None) -> None:
        self._transport = transport  # None -> synthetic transport per source

    def run(self, session: Session, tenant_id: int, source: str) -> SyncReport:
        from . import gorgias, interakt, judgeme, klaviyo, shopify  # lazy: mappers import this module

        mapper = {
            "shopify": shopify,
            "klaviyo": klaviyo,
            "interakt": interakt,
            "gorgias": gorgias,
            "judgeme": judgeme,
        }[source]
        started = datetime.utcnow()
        transport = self._transport
        if transport is None:
            from . import synthetic

            transport = synthetic.TRANSPORTS[source](session, tenant_id)

        resources: dict[str, int] = {}
        fetched = inserted_raw = skipped = 0
        for resource in mapper.RESOURCES:
            raw_source = mapper.RESOURCE_SOURCE[resource]
            existing = set(
                session.scalars(
                    select(RawRecord.external_id).where(
                        RawRecord.tenant_id == tenant_id,
                        RawRecord.source == raw_source,
                        RawRecord.resource == resource,
                    )
                )
            )
            cursor = self._get_cursor(session, tenant_id, source, resource)
            payloads: list[dict] = []
            while True:
                page, next_cursor = transport.fetch_page(resource, cursor)
                if not page:
                    break
                fetched += len(page)
                for payload in page:
                    ext = str(mapper.external_id(resource, payload))
                    if ext in existing:
                        skipped += 1
                    else:
                        session.add(
                            RawRecord(
                                tenant_id=tenant_id,
                                source=raw_source,
                                resource=resource,
                                external_id=ext,
                                payload=payload,
                            )
                        )
                        existing.add(ext)
                        inserted_raw += 1
                payloads.extend(page)
                if next_cursor is None:
                    break
                cursor = next_cursor
            resources[resource] = mapper.upsert(session, tenant_id, resource, payloads)
            self._set_cursor(session, tenant_id, source, resource, cursor)
        mapper.finalize(session, tenant_id)
        session.commit()
        return SyncReport(
            tenant_id=tenant_id,
            source=source,
            resources=resources,
            started_at=started,
            finished_at=datetime.utcnow(),
            fetched=fetched,
            inserted_raw=inserted_raw,
            skipped=skipped,
        )

    @staticmethod
    def _get_cursor(session: Session, tenant_id: int, source: str, resource: str) -> str | None:
        state = session.scalars(
            select(SyncState).filter_by(tenant_id=tenant_id, source=source, resource=resource)
        ).first()
        return state.cursor if state else None

    @staticmethod
    def _set_cursor(
        session: Session, tenant_id: int, source: str, resource: str, cursor: str | None
    ) -> None:
        state = session.scalars(
            select(SyncState).filter_by(tenant_id=tenant_id, source=source, resource=resource)
        ).first()
        if state is None:
            state = SyncState(tenant_id=tenant_id, source=source, resource=resource)
            session.add(state)
        state.cursor = cursor
        state.last_synced_at = datetime.utcnow()


# --------------------------------------------------------------------- shared helpers


def to_paise(amount: str | int | float | None) -> int:
    """Decimal-string RUPEES (Shopify money) -> integer paise. Never floats.

    Razorpay amounts are already integer paise — do NOT pass them through here.
    """
    if amount in (None, ""):
        return 0
    return int((Decimal(str(amount)) * 100).to_integral_value(rounding=ROUND_HALF_UP))


def parse_dt(value: str | int | float | None) -> datetime | None:
    """ISO-8601 (any offset) or unix epoch seconds -> naive UTC datetime."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):  # razorpay created_at is epoch seconds
        return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)
    dt = datetime.fromisoformat(str(value))
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def upsert_row(
    session: Session,
    model: type,
    tenant_id: int,
    source: str,
    external_id: str,
    values: dict,
) -> tuple[object, bool]:
    """Get-or-create keyed on (tenant_id, source, external_id); update in place.

    Returns (row, created). ponytail: per-row SELECT — batch-load the key set
    if seeder volumes ever make this the slow step.
    """
    obj = session.scalars(
        select(model).filter_by(tenant_id=tenant_id, source=source, external_id=external_id)
    ).first()
    if obj is None:
        obj = model(tenant_id=tenant_id, source=source, external_id=external_id, **values)
        session.add(obj)
        session.flush()
        return obj, True
    for key, val in values.items():
        setattr(obj, key, val)
    return obj, False


def ensure_identity(
    session: Session,
    tenant_id: int,
    customer_id: int,
    identity_type: str,
    identity_value: str | None,
    source: str,
) -> None:
    """Insert an identity handle unless (tenant, type, value) already exists.

    If the value is already claimed by ANOTHER customer we leave it in place —
    that co-occurrence is exactly the merge signal identity.resolve() consumes.
    """
    if not identity_value:
        return
    row = session.scalars(
        select(CustomerIdentity).filter_by(
            tenant_id=tenant_id, identity_type=identity_type, identity_value=str(identity_value)
        )
    ).first()
    if row is None:
        session.add(
            CustomerIdentity(
                tenant_id=tenant_id,
                customer_id=customer_id,
                identity_type=identity_type,
                identity_value=str(identity_value),
                source=source,
            )
        )
        session.flush()


def _lifecycle(orders_count: int, days_since_last: int) -> str:
    """CONTRACTS section 2.2 lifecycle rules. loyal wins over recency bands."""
    if orders_count >= 4 and days_since_last < 120:
        return "loyal"
    if days_since_last < 90:
        return "active" if orders_count >= 2 else "new"
    if days_since_last <= 180:
        return "slipping"
    if days_since_last <= 365:
        return "dormant"
    return "lost"


def recompute_customer_stats(session: Session, tenant_id: int) -> None:
    """Set-based rebuild of denormalized customer stats + customer_order_index.

    Cancelled orders are excluded from counts/spend/index (index -> NULL).
    Determinism: lifecycle "as of" is the tenant's max placed_at, not
    wall-clock — the synthetic dataset defines its own now.
    """
    as_of = session.scalar(select(func.max(Order.placed_at)).where(Order.tenant_id == tenant_id))
    if as_of is None:
        return
    rows = session.execute(
        select(Order.id, Order.customer_id, Order.placed_at, Order.total_paise, Order.cancelled_at)
        .where(Order.tenant_id == tenant_id, Order.customer_id.is_not(None))
        .order_by(Order.placed_at, Order.id)
    ).all()
    per_customer: dict[int, list[tuple[int, datetime, int]]] = {}
    seen: set[int] = set()
    order_updates: list[dict] = []
    for order_id, customer_id, placed_at, total_paise, cancelled_at in rows:
        seen.add(customer_id)
        if cancelled_at is not None:
            order_updates.append({"id": order_id, "customer_order_index": None})
            continue
        per_customer.setdefault(customer_id, []).append((order_id, placed_at, total_paise))
    customer_updates: list[dict] = []
    for customer_id in seen - per_customer.keys():
        # every order cancelled since the last sync -> zero the stale stats
        customer_updates.append(
            {
                "id": customer_id,
                "orders_count": 0,
                "total_spent_paise": 0,
                "first_order_at": None,
                "last_order_at": None,
                "lifecycle_stage": "new",
            }
        )
    for customer_id, seq in per_customer.items():
        for index, (order_id, _placed, _total) in enumerate(seq, start=1):
            order_updates.append({"id": order_id, "customer_order_index": index})
        last_at = seq[-1][1]
        days = (as_of - last_at).days
        customer_updates.append(
            {
                "id": customer_id,
                "orders_count": len(seq),
                "total_spent_paise": sum(t for _o, _p, t in seq),
                "first_order_at": seq[0][1],
                "last_order_at": last_at,
                "lifecycle_stage": _lifecycle(len(seq), days),
            }
        )
    if order_updates:
        session.execute(update(Order), order_updates)
    if customer_updates:
        session.execute(update(Customer), customer_updates)
    session.expire_all()  # bulk UPDATE bypasses the identity map
