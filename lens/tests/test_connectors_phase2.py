"""Phase-2 connector tests: interakt/gorgias/judgeme raw -> core, idempotent."""

from datetime import datetime

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
    Message,
    Order,
    RawRecord,
    Review,
    SupportTicket,
    Tenant,
)

RAW = [
    # shopify universe the new sources link against
    ("shopify", "customers", {
        "id": 101, "email": "Ananya.Iyer@Example.com", "phone": "98765 43210",
        "first_name": "Ananya", "last_name": "Iyer", "accepts_marketing": True,
        "created_at": "2025-01-05T10:00:00Z",
    }),
    ("shopify", "customers", {
        "id": 102, "email": "rohan@example.com", "phone": "9876500002",
        "first_name": "Rohan", "last_name": "Shah", "accepts_marketing": False,
        "created_at": "2025-02-01T09:00:00Z",
    }),
    ("shopify", "products", {
        "id": 11, "title": "Rose Water Toner", "product_type": "skincare",
        "vendor": "Meadow", "status": "active", "created_at": "2024-12-01T00:00:00Z",
        "variants": [{"id": 21, "sku": "MB-RWT-100", "title": "100ml",
                      "price": "499.00", "cost": "210.00"}],
    }),
    ("shopify", "orders", {
        "id": 5001, "name": "MB-1001", "created_at": "2026-05-01T10:00:00Z",
        "cancelled_at": None, "financial_status": "paid", "fulfillment_status": "fulfilled",
        "currency": "INR", "subtotal_paise": 140000, "discount_paise": 0,
        "shipping_paise": 0, "tax_paise": 0, "total_paise": 140000, "cod": False,
        "customer": {"id": 101}, "email": "ananya.iyer@example.com",
        "phone": "+919876543210", "line_items": [],
    }),
    ("shopify", "orders", {
        "id": 5002, "name": "MB-1002", "created_at": "2026-06-10T11:00:00Z",
        "cancelled_at": None, "financial_status": "pending", "fulfillment_status": None,
        "currency": "INR", "subtotal_paise": 80000, "discount_paise": 0,
        "shipping_paise": 0, "tax_paise": 0, "total_paise": 80000, "cod": True,
        "customer": {"id": 102}, "email": "rohan@example.com",
        "phone": "+919876500002", "line_items": [],
    }),
    # interakt (seeded shapes: read_at/failed_at, profile block)
    ("interakt", "campaigns", {
        "id": "IKC-1", "name": "Weekly WhatsApp Drop", "campaign_type": "campaign",
        "channel": "whatsapp", "started_at": "2026-06-01T10:00:00Z",
    }),
    ("interakt", "consent", {
        "id": "IKCON-101-g",
        "profile": {"id": "IK101", "phone": "+919876543210", "email": "ananya.iyer@example.com"},
        "channel": "whatsapp", "action": "granted", "method": "whatsapp_optin",
        "occurred_at": "2025-01-05T10:10:00Z",
    }),
    ("interakt", "messages", {
        "id": "WAM-1", "campaign_id": "IKC-1",
        "profile": {"id": "IK101", "phone": "+919876543210", "email": "ananya.iyer@example.com"},
        "channel": "whatsapp", "sent_at": "2026-06-01T10:05:00Z",
        "delivered_at": "2026-06-01T10:06:00Z", "read_at": "2026-06-01T12:00:00Z",
        "clicked_at": "2026-06-01T12:30:00Z", "failed_at": None,
    }),
    ("interakt", "messages", {  # send failure -> bounced_at
        "id": "WAM-2", "campaign_id": "IKC-1",
        "profile": {"id": "IK102", "phone": "+919876500002", "email": "rohan@example.com"},
        "channel": "whatsapp", "sent_at": "2026-06-01T10:05:00Z",
        "delivered_at": None, "read_at": None, "clicked_at": None,
        "failed_at": "2026-06-01T10:07:00Z",
    }),
    # gorgias
    ("gorgias", "tickets", {  # linked account customer + order
        "id": "GT-1", "order_external_id": "5002",
        "customer": {"external_id": "102"}, "email": "rohan@example.com", "phone": None,
        "channel": "email", "subject": "Where is my order?", "category": "delivery_delay",
        "status": "resolved", "opened_at": "2026-06-14T09:00:00Z",
        "first_response_at": "2026-06-14T11:00:00Z", "resolved_at": "2026-06-15T10:00:00Z",
        "csat": 4,
    }),
    ("gorgias", "tickets", {  # guest ticket: attaches via phone identity
        "id": "GT-2", "order_external_id": None,
        "customer": None, "email": None, "phone": "98765 43210",
        "channel": "whatsapp", "subject": "Product damaged", "category": "damaged",
        "status": "open", "opened_at": "2026-06-20T09:00:00Z",
        "first_response_at": None, "resolved_at": None, "csat": None,
    }),
    ("gorgias", "tickets", {  # unknown contact: lands with NULL customer_id
        "id": "GT-3", "order_external_id": None,
        "customer": None, "email": "stranger@example.com", "phone": None,
        "channel": "chat", "subject": "Random question", "category": "other",
        "status": "closed", "opened_at": "2026-06-21T09:00:00Z",
        "first_response_at": "2026-06-21T09:30:00Z", "resolved_at": "2026-06-21T10:00:00Z",
        "csat": None,
    }),
    # judgeme
    ("judgeme", "reviews", {
        "id": "JR-1", "order_external_id": "5001", "product_external_id": "11",
        "reviewer": {"external_id": "101", "email": "ananya.iyer@example.com",
                     "phone": "+919876543210"},
        "rating": 5, "title": "Lovely", "body": "Smells wonderful.", "verified": True,
        "submitted_at": "2026-05-20T10:00:00Z",
    }),
    ("judgeme", "reviews", {  # no matching order: review still lands, order_id NULL
        "id": "JR-2", "order_external_id": "9999", "product_external_id": "11",
        "reviewer": {"external_id": None, "email": "stranger@example.com", "phone": None},
        "rating": 2, "title": "Meh", "body": None, "verified": False,
        "submitted_at": "2026-06-25T10:00:00Z",
    }),
]


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        tenant = Tenant(slug="t2", name="T2")
        s.add(tenant)
        s.flush()
        for source, resource, payload in RAW:
            s.add(RawRecord(tenant_id=tenant.id, source=source, resource=resource,
                            external_id=str(payload["id"]), payload=payload))
        s.commit()
        yield s


def _shopify_customer(session: Session, ext: str) -> Customer:
    return session.scalars(select(Customer).filter_by(source="shopify", external_id=ext)).one()


def test_interakt_sync_maps_core(session: Session) -> None:
    SyncRunner().run(session, tenant_id=1, source="shopify")
    report = SyncRunner().run(session, tenant_id=1, source="interakt")
    assert report.resources == {"campaigns": 1, "consent": 1, "messages": 2}

    campaign = session.scalars(select(Campaign).filter_by(external_id="IKC-1")).one()
    assert campaign.channel == "whatsapp" and campaign.campaign_type == "campaign"
    assert campaign.started_at == datetime(2026, 6, 1, 10, 0)

    # profiles matched existing shopify customers by phone — none minted
    assert session.scalar(select(func.count()).select_from(Customer)) == 2
    c101 = _shopify_customer(session, "101")
    identities = {
        (i.identity_type, i.identity_value)
        for i in session.scalars(select(CustomerIdentity).filter_by(customer_id=c101.id))
    }
    assert ("interakt_profile_id", "IK101") in identities

    # consent ledger row + derived whatsapp flag
    ledger = session.scalars(select(ConsentLedger).filter_by(source="interakt")).one()
    assert ledger.customer_id == c101.id and ledger.channel == "whatsapp"
    assert c101.whatsapp_opted_in is True

    # funnel mapping: read_at -> opened_at, clicked_at kept, failed_at -> bounced_at
    wam1 = session.scalars(select(Message).filter_by(external_id="WAM-1")).one()
    assert wam1.channel == "whatsapp" and wam1.campaign_id == campaign.id
    assert wam1.customer_id == c101.id
    assert wam1.opened_at == datetime(2026, 6, 1, 12, 0)
    assert wam1.clicked_at == datetime(2026, 6, 1, 12, 30)
    assert wam1.bounced_at is None
    wam2 = session.scalars(select(Message).filter_by(external_id="WAM-2")).one()
    assert wam2.bounced_at == datetime(2026, 6, 1, 10, 7)
    assert wam2.delivered_at is None and wam2.opened_at is None


def test_gorgias_ticket_attaches_merged_customer(session: Session) -> None:
    SyncRunner().run(session, tenant_id=1, source="shopify")
    c101 = _shopify_customer(session, "101")
    c102 = _shopify_customer(session, "102")
    c102.merged_into_customer_id = c101.id  # simulate identity.resolve merge
    session.commit()

    report = SyncRunner().run(session, tenant_id=1, source="gorgias")
    assert report.resources == {"tickets": 3}

    # GT-1 names the absorbed customer 102: must land on the survivor 101
    gt1 = session.scalars(select(SupportTicket).filter_by(external_id="GT-1")).one()
    assert gt1.customer_id == c101.id
    order_5002 = session.scalars(select(Order).filter_by(external_id="5002")).one()
    assert gt1.order_id == order_5002.id
    assert gt1.category == "delivery_delay" and gt1.csat == 4
    assert gt1.opened_at == datetime(2026, 6, 14, 9, 0)
    assert gt1.resolved_at == datetime(2026, 6, 15, 10, 0)

    # GT-2: guest contact resolves via normalized phone
    gt2 = session.scalars(select(SupportTicket).filter_by(external_id="GT-2")).one()
    assert gt2.customer_id == c101.id and gt2.order_id is None

    # GT-3: unknown contact stays unresolved — no customer minted
    gt3 = session.scalars(select(SupportTicket).filter_by(external_id="GT-3")).one()
    assert gt3.customer_id is None
    assert session.scalar(select(func.count()).select_from(Customer)) == 2


def test_judgeme_review_without_order_lands_null(session: Session) -> None:
    SyncRunner().run(session, tenant_id=1, source="shopify")
    report = SyncRunner().run(session, tenant_id=1, source="judgeme")
    assert report.resources == {"reviews": 2}

    c101 = _shopify_customer(session, "101")
    order_5001 = session.scalars(select(Order).filter_by(external_id="5001")).one()
    jr1 = session.scalars(select(Review).filter_by(external_id="JR-1")).one()
    assert jr1.customer_id == c101.id and jr1.order_id == order_5001.id
    assert jr1.product_id is not None and jr1.rating == 5 and jr1.verified is True
    assert jr1.submitted_at == datetime(2026, 5, 20, 10, 0)

    jr2 = session.scalars(select(Review).filter_by(external_id="JR-2")).one()
    assert jr2.order_id is None  # unknown order: review still lands
    assert jr2.customer_id is None and jr2.verified is False
    assert jr2.product_id is not None


def test_phase2_resync_is_noop(session: Session) -> None:
    for source in ("shopify", "interakt", "gorgias", "judgeme"):
        SyncRunner().run(session, tenant_id=1, source=source)
    counts_before = {
        model: session.scalar(select(func.count()).select_from(model))
        for model in (Customer, CustomerIdentity, Campaign, Message, ConsentLedger,
                      SupportTicket, Review, RawRecord)
    }
    for source in ("interakt", "gorgias", "judgeme"):
        report = SyncRunner().run(session, tenant_id=1, source=source)
        assert report.fetched == 0 and report.inserted_raw == 0
        assert all(count == 0 for count in report.resources.values())
    counts_after = {
        model: session.scalar(select(func.count()).select_from(model))
        for model in counts_before
    }
    assert counts_after == counts_before
