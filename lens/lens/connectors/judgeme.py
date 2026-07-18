"""Judge.me (reviews) raw -> core mappers.

Raw shape the seeder lands (CONTRACTS.md V2.1):

judgeme/reviews::

    id, order_external_id, product_external_id,
    reviewer: {external_id | null, email, phone},
    rating (1-5), title, body (nullable), verified (bool), submitted_at

Maps to lens.models.Review. Product via (tenant, source='shopify',
external_id=product_external_id); order via order_external_id (NULL when the
order is unknown — a review still lands); customer linking as in gorgias
(shared ``gorgias._Maps.find_customer``: identity precedence, merge-pointer
following, NULL when unresolved — never mints customers).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Review
from .base import parse_dt
from .gorgias import _Maps

RESOURCES: tuple[str, ...] = ("reviews",)
RESOURCE_SOURCE: dict[str, str] = {r: "judgeme" for r in RESOURCES}


def external_id(resource: str, payload: dict) -> str:
    return str(payload["id"])


def upsert(session: Session, tenant_id: int, resource: str, payloads: list[dict]) -> int:
    if not payloads:
        return 0
    m = _Maps(session, tenant_id)
    existing = {
        r.external_id: r
        for r in session.scalars(
            select(Review).filter_by(tenant_id=tenant_id, source="judgeme")
        )
    }
    for payload in payloads:
        reviewer = payload.get("reviewer") or {}
        product_ext = payload.get("product_external_id")
        verified = payload.get("verified", True)
        if not isinstance(verified, bool):  # live judge.me: verified = "buyer" | "nothing"
            verified = str(verified).lower() == "buyer"
        values = {
            "customer_id": m.find_customer(
                reviewer.get("external_id"), reviewer.get("phone"), reviewer.get("email")
            ),
            "order_id": m.order_id(payload),
            "product_id": m.products.get(str(product_ext)) if product_ext is not None else None,
            "rating": int(payload.get("rating", 0)),
            "title": payload.get("title"),
            "body": payload.get("body"),
            "verified": verified,
            "submitted_at": parse_dt(payload.get("submitted_at") or payload.get("created_at")),
        }
        ext = str(payload["id"])
        row = existing.get(ext)
        if row is None:
            row = Review(tenant_id=tenant_id, source="judgeme", external_id=ext, **values)
            session.add(row)
            existing[ext] = row
        else:
            for key, val in values.items():
                setattr(row, key, val)
    session.flush()
    return len(payloads)


def finalize(session: Session, tenant_id: int) -> None:
    return None
