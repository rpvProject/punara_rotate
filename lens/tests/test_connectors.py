"""Connector pipeline tests: raw fixtures -> SyncRunner -> core rows, idempotent."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from lens.connectors.base import SyncRunner
from lens.models import (
    Base,
    Campaign,
    ConsentLedger,
    Customer,
    CustomerIdentity,
    CustomerPII,
    Message,
    Order,
    OrderItem,
    Payment,
    Product,
    RawRecord,
    Refund,
    Shipment,
    SyncState,
    Tenant,
    Variant,
)

EPOCH_PAY_OK = int(datetime(2026, 5, 1, 9, 50, tzinfo=timezone.utc).timestamp())

RAW = [
    # shopify/customers
    ("shopify", "customers", {
        "id": 101, "email": "Ananya.Iyer@Example.com", "phone": "98765 43210",
        "first_name": "Ananya", "last_name": "Iyer", "accepts_marketing": True,
        "created_at": "2025-01-05T10:00:00+05:30",
    }),
    ("shopify", "customers", {
        "id": 102, "email": "rohan@example.com", "phone": None,
        "first_name": "Rohan", "last_name": "Shah", "accepts_marketing": False,
        "created_at": "2025-02-01T09:00:00Z",
    }),
    # shopify/products
    ("shopify", "products", {
        "id": 11, "title": "Rose Water Toner", "product_type": "skincare",
        "vendor": "Meadow", "status": "active", "created_at": "2024-12-01T00:00:00Z",
        "variants": [{"id": 21, "sku": "MB-RWT-100", "title": "100ml",
                      "price": "499.00", "compare_at_price": "599.00", "cost": "210.00"}],
    }),
    # shopify/orders
    ("shopify", "orders", {
        "id": 5001, "name": "MB-1001", "created_at": "2026-05-01T10:00:00Z",
        "cancelled_at": None, "financial_status": "paid", "fulfillment_status": "fulfilled",
        "currency": "INR", "subtotal_price": "1400.00", "total_discounts": "100.00",
        "total_shipping_price_set": {"shop_money": {"amount": "50.00"}},
        "total_tax": "126.00", "total_price": "1476.00",
        "gateway": "razorpay", "payment_gateway_names": ["razorpay"],
        "customer": {"id": 101}, "email": "ananya.iyer@example.com", "phone": "+919876543210",
        "discount_codes": [{"code": "WELCOME10"}],
        "line_items": [{"id": 90001, "product_id": 11, "variant_id": 21, "sku": "MB-RWT-100",
                        "title": "Rose Water Toner 100ml", "quantity": 3, "price": "499.00",
                        "total_discount": "100.00"}],
        "refunds": [{"id": 9001, "created_at": "2026-05-10T10:00:00Z", "note": "return",
                     "transactions": [{"amount": "476.00", "gateway": "razorpay"}]}],
        "fulfillments": [{"created_at": "2026-05-02T09:00:00Z"}],
    }),
    ("shopify", "orders", {
        "id": 5002, "name": "MB-1002", "created_at": "2026-06-10T11:00:00Z",
        "cancelled_at": None, "financial_status": "pending", "fulfillment_status": None,
        "currency": "INR", "subtotal_price": "800.00", "total_discounts": "0.00",
        "total_tax": "0.00", "total_price": "800.00",
        "payment_gateway_names": ["Cash on Delivery (COD)"],
        "customer": {"id": 101}, "email": "ananya.iyer@example.com", "phone": "+919876543210",
        "line_items": [{"id": 90002, "product_id": 11, "variant_id": 21, "sku": "MB-RWT-100",
                        "title": "Rose Water Toner 100ml", "quantity": 2, "price": "400.00",
                        "total_discount": "0.00"}],
    }),
    ("shopify", "orders", {  # guest checkout: attaches only via identity.resolve()
        "id": 5003, "name": "MB-1003", "created_at": "2026-06-20T12:00:00Z",
        "cancelled_at": None, "financial_status": "paid", "fulfillment_status": None,
        "currency": "INR", "subtotal_price": "500.00", "total_discounts": "0.00",
        "total_tax": "0.00", "total_price": "500.00",
        "gateway": "razorpay", "payment_gateway_names": ["razorpay"],
        "customer": None, "email": "Guest@Example.com", "phone": "09876500001",
        "line_items": [],
    }),
    # razorpay/payments (amount = native integer paise)
    ("razorpay", "payments", {
        "id": "pay_ok", "amount": 147600, "currency": "INR", "status": "captured",
        "method": "upi", "error_description": None, "created_at": EPOCH_PAY_OK,
        "notes": {"shopify_order_id": "5001"},
    }),
    ("razorpay", "payments", {
        "id": "pay_fail", "amount": 147600, "currency": "INR", "status": "failed",
        "method": "card", "error_description": "card_declined",
        "created_at": "2026-05-01T09:45:00Z", "notes": {"shopify_order_id": "5001"},
    }),
    ("razorpay", "payments", {
        "id": "pay_guest", "amount": 50000, "currency": "INR", "status": "captured",
        "method": "upi", "error_description": None, "created_at": "2026-06-20T12:01:00Z",
        "notes": {"shopify_order_id": "5003"},
    }),
    # shiprocket/shipments
    ("shiprocket", "shipments", {
        "id": 33001, "order_id": "5001", "courier": "Delhivery", "status": "DELIVERED",
        "shipped_date": "2026-05-02 10:00:00", "delivered_date": "2026-05-05 14:00:00",
        "rto_delivered_date": None,
    }),
    ("shiprocket", "shipments", {
        "id": 33002, "order_id": "5002", "courier": "Bluedart", "status": "RTO DELIVERED",
        "shipped_date": "2026-06-11 10:00:00", "delivered_date": None,
        "rto_delivered_date": "2026-06-25 12:00:00",
    }),
    # klaviyo
    ("klaviyo", "campaigns", {
        "id": "camp_1", "name": "June Winback", "type": "campaign", "channel": "email",
        "subject": "We miss you", "send_time": "2026-06-01T10:00:00Z",
    }),
    ("klaviyo", "consent", {
        "id": "cons_1", "profile_id": "prof_101", "email": "ananya.iyer@example.com",
        "phone_number": "+919876543210", "external_id": "101", "channel": "whatsapp",
        "action": "granted", "method": "checkout", "occurred_at": "2026-05-01T10:05:00Z",
    }),
    ("klaviyo", "consent", {
        "id": "cons_2", "profile_id": "prof_101", "email": "ananya.iyer@example.com",
        "phone_number": "+919876543210", "external_id": "101", "channel": "email",
        "action": "granted", "method": "checkout", "occurred_at": "2026-05-01T10:05:00Z",
    }),
    ("klaviyo", "consent", {  # later revoke wins over the earlier email grant
        "id": "cons_3", "profile_id": "prof_101", "email": "ananya.iyer@example.com",
        "phone_number": "+919876543210", "external_id": "101", "channel": "email",
        "action": "revoked", "method": "unsubscribe_link", "occurred_at": "2026-06-15T08:00:00Z",
    }),
    ("klaviyo", "messages", {
        "id": "msg_1", "campaign_id": "camp_1", "profile_id": "prof_101", "channel": "email",
        "sent_at": "2026-06-01T10:00:00Z", "delivered_at": "2026-06-01T10:01:00Z",
        "opened_at": "2026-06-01T12:00:00Z", "clicked_at": None, "bounced_at": None,
        "unsubscribed_at": None,
    }),
]


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        tenant = Tenant(slug="t1", name="T1")
        s.add(tenant)
        s.flush()
        for source, resource, payload in RAW:
            s.add(RawRecord(tenant_id=tenant.id, source=source, resource=resource,
                            external_id=str(payload["id"]), payload=payload))
        s.commit()
        yield s


def _shopify_customer(session: Session, ext: str) -> Customer:
    return session.scalars(select(Customer).filter_by(source="shopify", external_id=ext)).one()


def test_shopify_sync_maps_core(session: Session) -> None:
    report = SyncRunner().run(session, tenant_id=1, source="shopify")
    assert report.resources == {"customers": 2, "products": 1, "orders": 3,
                                "payments": 3, "shipments": 2}

    # customers + PII + identities; tz-aware source timestamps land as naive UTC
    c101 = _shopify_customer(session, "101")
    assert c101.created_at == datetime(2025, 1, 5, 4, 30)
    assert c101.accepts_email_marketing is True
    pii = session.get(CustomerPII, c101.id)
    assert pii.primary_email == "ananya.iyer@example.com"
    assert pii.primary_phone == "+919876543210"
    identities = {
        (i.identity_type, i.identity_value)
        for i in session.scalars(select(CustomerIdentity).filter_by(customer_id=c101.id))
    }
    assert ("shopify_customer_id", "101") in identities
    assert ("phone", "+919876543210") in identities
    assert ("email", "ananya.iyer@example.com") in identities

    # catalog money in paise
    variant = session.scalars(select(Variant).filter_by(external_id="21")).one()
    assert (variant.price_paise, variant.compare_at_price_paise, variant.cost_paise) == (
        49900, 59900, 21000)

    # orders: money, COD detection, discount codes
    o1 = session.scalars(select(Order).filter_by(external_id="5001")).one()
    assert (o1.subtotal_paise, o1.discount_paise, o1.shipping_paise,
            o1.tax_paise, o1.total_paise) == (140000, 10000, 5000, 12600, 147600)
    assert o1.placed_at == datetime(2026, 5, 1, 10, 0)
    assert o1.cod is False and o1.discount_codes == "WELCOME10"
    o2 = session.scalars(select(Order).filter_by(external_id="5002")).one()
    assert o2.cod is True
    o3 = session.scalars(select(Order).filter_by(external_id="5003")).one()
    assert o3.customer_id is None  # guest stays unresolved until identity.resolve

    # line items snapshot variant cost
    item = session.scalars(select(OrderItem).filter_by(order_id=o1.id)).one()
    assert (item.quantity, item.unit_price_paise, item.discount_paise,
            item.unit_cost_paise) == (3, 49900, 10000, 21000)
    assert item.product_id is not None and item.variant_id is not None

    # refund from the order payload
    refund = session.scalars(select(Refund).filter_by(external_id="9001")).one()
    assert (refund.amount_paise, refund.refund_type, refund.order_id) == (47600, "return", o1.id)

    # razorpay payments (native paise; epoch + ISO timestamps both parse)
    pay_ok = session.scalars(select(Payment).filter_by(external_id="pay_ok")).one()
    assert pay_ok.amount_paise == 147600 and pay_ok.order_id == o1.id
    assert pay_ok.occurred_at == datetime(2026, 5, 1, 9, 50)
    pay_fail = session.scalars(select(Payment).filter_by(external_id="pay_fail")).one()
    assert pay_fail.status == "failed" and pay_fail.failure_reason == "card_declined"

    # shiprocket shipments update the order's fulfillment lifecycle
    assert session.get(Order, o1.id).fulfillment_status == "delivered"
    assert session.get(Order, o1.id).delivered_at == datetime(2026, 5, 5, 14, 0)
    ship_rto = session.scalars(select(Shipment).filter_by(external_id="33002")).one()
    assert ship_rto.rto is True and ship_rto.status == "rto_received"
    assert session.get(Order, o2.id).fulfillment_status == "rto"

    # denormalized stats + lifecycle (as_of = tenant max placed_at = 2026-06-20)
    c101 = _shopify_customer(session, "101")
    assert c101.orders_count == 2 and c101.total_spent_paise == 227600
    assert c101.first_order_at == datetime(2026, 5, 1, 10, 0)
    assert c101.last_order_at == datetime(2026, 6, 10, 11, 0)
    assert c101.lifecycle_stage == "active"
    assert session.get(Order, o1.id).customer_order_index == 1
    assert session.get(Order, o2.id).customer_order_index == 2
    c102 = _shopify_customer(session, "102")
    assert c102.orders_count == 0 and c102.lifecycle_stage == "new"

    # sync_state cursor per resource
    states = session.scalars(select(SyncState).filter_by(tenant_id=1, source="shopify")).all()
    assert len(states) == 5 and all(st.cursor is not None for st in states)


def test_klaviyo_sync_maps_core(session: Session) -> None:
    SyncRunner().run(session, tenant_id=1, source="shopify")
    report = SyncRunner().run(session, tenant_id=1, source="klaviyo")
    assert report.resources == {"campaigns": 1, "consent": 3, "messages": 1}

    campaign = session.scalars(select(Campaign).filter_by(external_id="camp_1")).one()
    assert campaign.started_at == datetime(2026, 6, 1, 10, 0)

    # profile attached to the existing shopify customer — no new customer minted
    assert session.scalar(select(func.count()).select_from(Customer)) == 2
    c101 = _shopify_customer(session, "101")
    identities = {
        (i.identity_type, i.identity_value)
        for i in session.scalars(select(CustomerIdentity).filter_by(customer_id=c101.id))
    }
    assert ("klaviyo_profile_id", "prof_101") in identities

    # append-only ledger; last action per channel wins on the flags
    assert session.scalar(select(func.count()).select_from(ConsentLedger)) == 3
    assert c101.whatsapp_opted_in is True
    assert c101.accepts_email_marketing is False  # cons_3 revoked email later

    message = session.scalars(select(Message).filter_by(external_id="msg_1")).one()
    assert message.customer_id == c101.id and message.campaign_id == campaign.id
    assert message.opened_at == datetime(2026, 6, 1, 12, 0)


def test_resync_is_noop(session: Session) -> None:
    SyncRunner().run(session, tenant_id=1, source="shopify")
    SyncRunner().run(session, tenant_id=1, source="klaviyo")
    counts_before = {
        model: session.scalar(select(func.count()).select_from(model))
        for model in (Customer, CustomerIdentity, Product, Variant, Order, OrderItem,
                      Refund, Payment, Shipment, Campaign, Message, ConsentLedger, RawRecord)
    }
    second_shopify = SyncRunner().run(session, tenant_id=1, source="shopify")
    second_klaviyo = SyncRunner().run(session, tenant_id=1, source="klaviyo")
    for report in (second_shopify, second_klaviyo):
        assert report.fetched == 0 and report.inserted_raw == 0
        assert all(count == 0 for count in report.resources.values())
    counts_after = {
        model: session.scalar(select(func.count()).select_from(model))
        for model in counts_before
    }
    assert counts_after == counts_before
