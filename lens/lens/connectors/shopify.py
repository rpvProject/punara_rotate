"""Shopify / Razorpay / Shiprocket raw -> core mappers.

The "shopify" sync run ingests all three sources: Razorpay payments and
Shiprocket shipments attach to Shopify orders (CONTRACTS section 2.2).

Payload subsets consumed — field names follow each source's public API:

shopify/customers — Admin REST ``GET /customers.json`` -> ``customers[]``::

    id, email, phone, first_name, last_name, accepts_marketing, created_at

shopify/products — ``GET /products.json`` -> ``products[]``::

    id, title, product_type, vendor, status, created_at,
    variants[]: id, sku, title, price, compare_at_price,
                cost  (v0 extension: the real API keeps cost on InventoryItem)

shopify/orders — ``GET /orders.json`` -> ``orders[]``::

    id, name, order_number, created_at, cancelled_at,
    financial_status (pending|authorized|paid|partially_refunded|refunded|voided),
    fulfillment_status (null|"partial"|"fulfilled"), currency,
    subtotal_price, total_discounts, total_tax, total_price,
    total_shipping_price_set.shop_money.amount (flat total_shipping_price ok),
    gateway, payment_gateway_names[]  (COD detection: any name containing
        "cod" / "cash on delivery" / "cash_on_delivery", case-insensitive),
    customer: {id, ...} | null  (null = guest checkout),
    email, phone  (guest contact; identity.resolve() attaches these later),
    discount_codes[]: {code},
    line_items[]: id, product_id, variant_id, sku, title, quantity, price,
                  total_discount,
    refunds[]: id, created_at, note (refund_type hint:
               return|rto|goodwill|payment_failure),
               transactions[]: {amount, gateway},
    fulfillments[]: {created_at}

razorpay/payments — Payments API entity (amounts NATIVELY integer paise)::

    id, amount, currency, status (created|authorized|captured|failed|refunded),
    method (upi|card|netbanking|wallet|cod), error_description,
    created_at (unix epoch seconds; ISO strings also accepted),
    notes.shopify_order_id  (v0 seam linking the payment to its order)

shiprocket/shipments::

    id, order_id (shopify order external id), courier,
    status (PICKUP SCHEDULED|IN TRANSIT|DELIVERED|RTO INITIATED|
            RTO DELIVERED|LOST),
    shipped_date, delivered_date, rto_delivered_date

Money: Shopify money fields are decimal-string RUPEES -> ``to_paise()``.
Razorpay amounts are already integer paise and pass through untouched.

Seeded raw payloads (CONTRACTS.md section 2.1) use the repo money convention
instead of source cosplay: integer ``*_paise`` keys, ``order_external_id`` on
razorpay/shiprocket rows, an explicit ``cod`` bool, variants keyed by
``external_id``, ``refund_type``/``processed_at`` on embedded refunds, and
``shipped_at``/``delivered_at``/``rto_at`` on shipments. Every mapper
dual-reads: the ``*_paise``/contract key wins when present, else the
public-API key is parsed.

Mappers prefetch existing rows into per-batch maps (see ``_Maps``) so a sync
issues a handful of bulk SELECTs instead of one per record.
"""

from __future__ import annotations

from functools import cached_property

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..identity import normalize_email, normalize_phone
from ..models import (
    Customer,
    CustomerIdentity,
    CustomerPII,
    Order,
    OrderItem,
    Payment,
    Product,
    Refund,
    Shipment,
    Variant,
)
from .base import parse_dt, recompute_customer_stats, to_paise

RESOURCES: tuple[str, ...] = ("customers", "products", "orders", "payments", "shipments")
RESOURCE_SOURCE: dict[str, str] = {
    "customers": "shopify",
    "products": "shopify",
    "orders": "shopify",
    "payments": "razorpay",
    "shipments": "shiprocket",
}

_COD_MARKERS = ("cod", "cash on delivery", "cash_on_delivery")
_REFUND_TYPES = {"return", "rto", "goodwill", "payment_failure"}
_SHIP_STATUS = {
    "PICKUP SCHEDULED": "pending",
    "PICKUP_SCHEDULED": "pending",
    "PENDING": "pending",
    "IN TRANSIT": "in_transit",
    "IN_TRANSIT": "in_transit",
    "DELIVERED": "delivered",
    "RTO INITIATED": "rto_initiated",
    "RTO_INITIATED": "rto_initiated",
    "RTO DELIVERED": "rto_received",
    "RTO_DELIVERED": "rto_received",
    "RTO RECEIVED": "rto_received",
    "RTO_RECEIVED": "rto_received",
    "LOST": "lost",
}


def _money(payload: dict, paise_key: str, rupee_key: str) -> int:
    """Contract integer-paise key wins; else parse the decimal-rupee API key."""
    if payload.get(paise_key) is not None:
        return int(payload[paise_key])
    return to_paise(payload.get(rupee_key))


def external_id(resource: str, payload: dict) -> str:
    return str(payload["id"])


class _Maps:
    """Lazy per-batch prefetch of existing rows, keyed by external_id.

    ponytail: full-table maps per tenant — fine at v0 scale (~10^5 rows);
    the upgrade path is keyed IN-chunk prefetch of just the batch's ids.
    """

    def __init__(self, session: Session, tenant_id: int) -> None:
        self._session = session
        self._tid = tenant_id

    def _by_ext(self, model) -> dict:  # noqa: ANN001
        return {
            row.external_id: row
            for row in self._session.scalars(select(model).where(model.tenant_id == self._tid))
        }

    @cached_property
    def customers(self) -> dict[str, Customer]:
        return {
            c.external_id: c
            for c in self._session.scalars(
                select(Customer).filter_by(tenant_id=self._tid, source="shopify")
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

    @cached_property
    def identities(self) -> set[tuple[str, str]]:
        return {
            (i.identity_type, i.identity_value)
            for i in self._session.scalars(
                select(CustomerIdentity).where(CustomerIdentity.tenant_id == self._tid)
            )
        }

    @cached_property
    def products(self) -> dict[str, Product]:
        return self._by_ext(Product)

    @cached_property
    def variants(self) -> dict[str, Variant]:
        return self._by_ext(Variant)

    @cached_property
    def orders(self) -> dict[str, Order]:
        return self._by_ext(Order)

    @cached_property
    def refunds(self) -> dict[str, Refund]:
        return self._by_ext(Refund)

    @cached_property
    def payments(self) -> dict[str, Payment]:
        return self._by_ext(Payment)

    @cached_property
    def shipments(self) -> dict[str, Shipment]:
        return self._by_ext(Shipment)


def upsert(session: Session, tenant_id: int, resource: str, payloads: list[dict]) -> int:
    if not payloads:
        return 0
    fn = {
        "customers": _customers,
        "products": _products,
        "orders": _orders,
        "payments": _payments,
        "shipments": _shipments,
    }[resource]
    return fn(session, tenant_id, payloads, _Maps(session, tenant_id))


def finalize(session: Session, tenant_id: int) -> None:
    recompute_customer_stats(session, tenant_id)


def _add_identity(
    session: Session,
    tenant_id: int,
    customer_id: int,
    identity_type: str,
    identity_value: str | None,
    m: _Maps,
) -> None:
    """Insert an identity handle unless (tenant, type, value) already exists.

    If the value is already claimed by ANOTHER customer we leave it in place —
    that co-occurrence is exactly the merge signal identity.resolve() consumes.
    """
    if not identity_value:
        return
    key = (identity_type, str(identity_value))
    if key in m.identities:
        return
    session.add(
        CustomerIdentity(
            tenant_id=tenant_id,
            customer_id=customer_id,
            identity_type=identity_type,
            identity_value=str(identity_value),
            source="shopify",
        )
    )
    m.identities.add(key)


# ------------------------------------------------------------------------- customers


def _ensure_customer(session: Session, tenant_id: int, payload: dict, m: _Maps) -> Customer:
    """Upsert customer + PII + identities from a (possibly partial) customer object."""
    ext = str(payload["id"])
    customer = m.customers.get(ext)
    if customer is None:
        customer = Customer(tenant_id=tenant_id, source="shopify", external_id=ext)
        session.add(customer)
        session.flush()  # id needed for PII/identities
    while customer.merged_into_customer_id is not None:  # follow merge pointers
        customer = session.get(Customer, customer.merged_into_customer_id)
    m.customers[ext] = customer
    if "accepts_marketing" in payload:  # partial embeds must not reset the flag
        customer.accepts_email_marketing = bool(payload["accepts_marketing"])
    created = parse_dt(payload.get("created_at"))
    if created is not None:
        customer.created_at = created

    phone = normalize_phone(payload.get("phone"))
    email = normalize_email(payload.get("email"))
    if phone or email or payload.get("first_name") or payload.get("last_name"):
        pii = m.pii.get(customer.id)
        if pii is None:
            pii = CustomerPII(customer_id=customer.id, tenant_id=tenant_id)
            session.add(pii)
            m.pii[customer.id] = pii
        if email:
            pii.primary_email = email
        if phone:
            pii.primary_phone = phone
        if payload.get("first_name"):
            pii.first_name = payload["first_name"]
        if payload.get("last_name"):
            pii.last_name = payload["last_name"]
    _add_identity(session, tenant_id, customer.id, "shopify_customer_id", ext, m)
    _add_identity(session, tenant_id, customer.id, "phone", phone, m)
    _add_identity(session, tenant_id, customer.id, "email", email, m)
    return customer


def _customers(session: Session, tenant_id: int, payloads: list[dict], m: _Maps) -> int:
    # pass 1: create missing rows so ids land in ONE flush, not one per row
    for payload in payloads:
        ext = str(payload["id"])
        if ext not in m.customers:
            customer = Customer(tenant_id=tenant_id, source="shopify", external_id=ext)
            session.add(customer)
            m.customers[ext] = customer
    session.flush()
    for payload in payloads:
        _ensure_customer(session, tenant_id, payload, m)
    return len(payloads)


# --------------------------------------------------------------------------- catalog


def _products(session: Session, tenant_id: int, payloads: list[dict], m: _Maps) -> int:
    for payload in payloads:
        ext = str(payload["id"])
        product = m.products.get(ext)
        if product is None:
            product = Product(tenant_id=tenant_id, source="shopify", external_id=ext, title="")
            session.add(product)
            session.flush()  # id needed for variants
            m.products[ext] = product
        product.title = payload.get("title", "")
        product.product_type = payload.get("product_type")
        product.vendor = payload.get("vendor")
        product.status = payload.get("status", "active")
        created = parse_dt(payload.get("created_at"))
        if created is not None:
            product.created_at = created
        for var in payload.get("variants") or []:
            vext = str(var.get("id") or var["external_id"])  # seeded variants: external_id
            variant = m.variants.get(vext)
            if variant is None:
                variant = Variant(
                    tenant_id=tenant_id, source="shopify", external_id=vext,
                    product_id=product.id,
                )
                session.add(variant)
                m.variants[vext] = variant
            variant.product_id = product.id
            variant.sku = var.get("sku")
            variant.title = var.get("title")
            variant.price_paise = _money(var, "price_paise", "price")
            variant.compare_at_price_paise = (
                _money(var, "compare_at_price_paise", "compare_at_price")
                if (var.get("compare_at_price_paise") or var.get("compare_at_price"))
                else None
            )
            variant.cost_paise = (
                _money(var, "cost_paise", "cost")
                if (var.get("cost_paise") or var.get("cost"))
                else None
            )
    session.flush()
    return len(payloads)


# ---------------------------------------------------------------------------- orders


def _is_cod(payload: dict) -> bool:
    if "cod" in payload:  # seeded payloads carry the bool first-class
        return bool(payload["cod"])
    names = [str(g) for g in (payload.get("payment_gateway_names") or [])]
    for key in ("gateway", "payment_gateway"):
        if payload.get(key):
            names.append(str(payload[key]))
    return any(marker in name.lower() for name in names for marker in _COD_MARKERS)


def _order_values(payload: dict) -> dict:
    if payload.get("shipping_paise") is not None:
        shipping_paise = int(payload["shipping_paise"])
    else:
        shipping_paise = to_paise(
            payload.get("total_shipping_price")
            or ((payload.get("total_shipping_price_set") or {}).get("shop_money") or {}).get(
                "amount"
            )
        )
    fulfillments = payload.get("fulfillments") or []
    raw_fstatus = payload.get("fulfillment_status")
    fulfillment_status = {None: "unfulfilled", "partial": "partial", "fulfilled": "fulfilled"}.get(
        raw_fstatus, raw_fstatus or "unfulfilled"
    )
    codes = ",".join(  # discount_codes: [{code}] (Shopify) or plain strings (seeded)
        d.get("code", "") if isinstance(d, dict) else str(d)
        for d in payload.get("discount_codes") or []
    ) or None
    gateways = payload.get("payment_gateway_names") or [
        payload.get("gateway") or payload.get("payment_gateway")
    ]
    return {
        "order_number": str(payload.get("name") or payload.get("order_number") or ""),
        "placed_at": parse_dt(payload.get("created_at")),
        "cancelled_at": parse_dt(payload.get("cancelled_at")),
        "fulfilled_at": parse_dt(fulfillments[0].get("created_at")) if fulfillments else None,
        "financial_status": payload.get("financial_status") or "pending",
        "fulfillment_status": fulfillment_status,
        "cod": _is_cod(payload),
        "payment_gateway": gateways[0],
        "subtotal_paise": _money(payload, "subtotal_paise", "subtotal_price"),
        "discount_paise": _money(payload, "discount_paise", "total_discounts"),
        "shipping_paise": shipping_paise,
        "tax_paise": _money(payload, "tax_paise", "total_tax"),
        "total_paise": _money(payload, "total_paise", "total_price"),
        "currency": payload.get("currency", "INR"),
        "discount_codes": codes,
    }


def _orders(session: Session, tenant_id: int, payloads: list[dict], m: _Maps) -> int:
    # pass 1: upsert order rows (ids land in one flush)
    for payload in payloads:
        customer_id: int | None = None
        embedded = payload.get("customer")
        if embedded and embedded.get("id") is not None:
            customer_id = _ensure_customer(session, tenant_id, embedded, m).id
        values = _order_values(payload)
        ext = str(payload["id"])
        order = m.orders.get(ext)
        if order is None or customer_id is not None:
            # guest payload re-delivery must not wipe the customer that
            # identity.resolve() previously attached
            values["customer_id"] = customer_id
        if order is None:
            order = Order(tenant_id=tenant_id, source="shopify", external_id=ext, **values)
            session.add(order)
            m.orders[ext] = order
        else:
            for key, val in values.items():
                setattr(order, key, val)
    session.flush()

    # pass 2: line items (no stable key -> delete + reinsert, idempotent) + refunds
    order_ids = [m.orders[str(p["id"])].id for p in payloads]
    for i in range(0, len(order_ids), 5000):  # stay under SQLite's parameter cap
        session.query(OrderItem).filter(
            OrderItem.tenant_id == tenant_id, OrderItem.order_id.in_(order_ids[i : i + 5000])
        ).delete(synchronize_session=False)
    for payload in payloads:
        order = m.orders[str(payload["id"])]
        for item in payload.get("line_items") or []:
            product_ext = item.get("product_id") or item.get("product_external_id")
            variant_ext = item.get("variant_id") or item.get("variant_external_id")
            product = m.products.get(str(product_ext)) if product_ext is not None else None
            variant = m.variants.get(str(variant_ext)) if variant_ext is not None else None
            session.add(
                OrderItem(
                    tenant_id=tenant_id,
                    order_id=order.id,
                    product_id=product.id if product else None,
                    variant_id=variant.id if variant else None,
                    sku=item.get("sku"),
                    title=item.get("title"),
                    quantity=int(item.get("quantity", 1)),
                    unit_price_paise=_money(item, "unit_price_paise", "price"),
                    discount_paise=_money(item, "discount_paise", "total_discount"),
                    unit_cost_paise=variant.cost_paise if variant else None,
                )
            )
        for refund in payload.get("refunds") or []:
            transactions = refund.get("transactions") or []
            hint = (refund.get("refund_type") or refund.get("note") or "").strip().lower()
            if refund.get("amount_paise") is not None:
                amount_paise = int(refund["amount_paise"])
            else:
                amount_paise = sum(to_paise(t.get("amount")) for t in transactions)
            values = {
                "order_id": order.id,
                "customer_id": order.customer_id,
                "amount_paise": amount_paise,
                "currency": payload.get("currency", "INR"),
                "refund_type": hint if hint in _REFUND_TYPES else "return",
                "processed_at": parse_dt(refund.get("processed_at") or refund.get("created_at")),
                "gateway": transactions[0].get("gateway") if transactions else None,
            }
            rext = str(refund["id"])
            row = m.refunds.get(rext)
            if row is None:
                row = Refund(tenant_id=tenant_id, source="shopify", external_id=rext, **values)
                session.add(row)
                m.refunds[rext] = row
            else:
                for key, val in values.items():
                    setattr(row, key, val)
    session.flush()
    return len(payloads)


# -------------------------------------------------------------------------- payments


def _payments(session: Session, tenant_id: int, payloads: list[dict], m: _Maps) -> int:
    for payload in payloads:
        order = None
        order_ext = payload.get("order_external_id") or (payload.get("notes") or {}).get(
            "shopify_order_id"
        )
        if order_ext is not None:
            order = m.orders.get(str(order_ext))
        values = {
            "order_id": order.id if order else None,
            "method": payload.get("method", "upi"),
            "gateway": "razorpay",
            "status": payload.get("status", "created"),
            # razorpay `amount` is ALREADY paise; seeded rows say amount_paise
            "amount_paise": int(payload.get("amount_paise", payload.get("amount", 0))),
            "currency": payload.get("currency", "INR"),
            "failure_reason": payload.get("failure_reason") or payload.get("error_description"),
            "occurred_at": parse_dt(payload.get("created_at")),
        }
        ext = str(payload["id"])
        row = m.payments.get(ext)
        if row is None:
            row = Payment(tenant_id=tenant_id, source="razorpay", external_id=ext, **values)
            session.add(row)
            m.payments[ext] = row
        else:
            for key, val in values.items():
                setattr(row, key, val)
    session.flush()
    return len(payloads)


# ------------------------------------------------------------------------- shipments


def _shipments(session: Session, tenant_id: int, payloads: list[dict], m: _Maps) -> int:
    upserted = 0
    for payload in payloads:
        order_ext = payload.get("order_external_id") or payload.get("order_id")
        order = m.orders.get(str(order_ext))
        if order is None:
            # ponytail: orphan shipment skipped (orders sync always runs first in
            # the same pass); a dead-letter table is the upgrade path if real
            # sources ever deliver shipments before orders.
            continue
        status = _SHIP_STATUS.get(str(payload.get("status", "")).upper(), "pending")
        rto = bool(payload.get("rto")) or status.startswith("rto")
        shipped_at = parse_dt(payload.get("shipped_at") or payload.get("shipped_date"))
        delivered_at = parse_dt(payload.get("delivered_at") or payload.get("delivered_date"))
        rto_at = parse_dt(payload.get("rto_at") or payload.get("rto_delivered_date"))
        values = {
            "order_id": order.id,
            "courier": payload.get("courier"),
            "status": status,
            "rto": rto,
            "shipped_at": shipped_at,
            "delivered_at": delivered_at,
            "rto_at": rto_at,
        }
        ext = str(payload["id"])
        row = m.shipments.get(ext)
        if row is None:
            row = Shipment(tenant_id=tenant_id, source="shiprocket", external_id=ext, **values)
            session.add(row)
            m.shipments[ext] = row
        else:
            for key, val in values.items():
                setattr(row, key, val)
        if shipped_at is not None and order.fulfilled_at is None:
            order.fulfilled_at = shipped_at
        if status == "delivered":
            order.delivered_at = delivered_at or order.delivered_at
            order.fulfillment_status = "delivered"
        elif rto:
            order.fulfillment_status = "rto"
        upserted += 1
    session.flush()
    return upserted
