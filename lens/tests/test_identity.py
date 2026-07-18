"""Identity resolution tests: normalization tables + the guest-order merge case."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from lens.identity import ResolveReport, normalize_email, normalize_phone, resolve
from lens.models import (
    Base,
    Customer,
    CustomerIdentity,
    CustomerPII,
    IdentityEdge,
    Order,
    RawRecord,
    Tenant,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("9876543210", "+919876543210"),          # bare Indian mobile
        ("09876543210", "+919876543210"),         # trunk 0
        ("919876543210", "+919876543210"),        # 91 prefix, no +
        ("+91 98765-43210", "+919876543210"),     # punctuation/whitespace
        ("0091 9876543210", "+919876543210"),     # 00 international prefix
        ("+14155552671", "+14155552671"),         # non-Indian E.164 passthrough
        ("5555555555", None),                     # 10 digits, invalid mobile prefix
        ("12345", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_phone(raw: str | None, expected: str | None) -> None:
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Ananya.Iyer@Example.COM ", "ananya.iyer@example.com"),
        ("not-an-email", None),
        ("a@b", None),  # no dot in domain
        ("", None),
        (None, None),
    ],
)
def test_normalize_email(raw: str | None, expected: str | None) -> None:
    assert normalize_email(raw) == expected


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        s.add(Tenant(slug="t1", name="T1"))
        s.flush()
        yield s


def _merge_fixture(s: Session) -> tuple[Customer, Customer, Order, Order]:
    """Shopify email account + klaviyo phone-only profile + guest order bridging both."""
    account = Customer(tenant_id=1, source="shopify", external_id="201",
                       created_at=datetime(2025, 1, 1))
    ghost = Customer(tenant_id=1, source="klaviyo", external_id="prof_9",
                     created_at=datetime(2026, 2, 1))
    s.add_all([account, ghost])
    s.flush()
    s.add_all([
        CustomerPII(customer_id=account.id, tenant_id=1, primary_email="e@x.com",
                    first_name="Ananya"),
        CustomerPII(customer_id=ghost.id, tenant_id=1, primary_phone="+919876500001"),
        CustomerIdentity(tenant_id=1, customer_id=account.id,
                         identity_type="shopify_customer_id", identity_value="201",
                         source="shopify"),
        CustomerIdentity(tenant_id=1, customer_id=account.id, identity_type="email",
                         identity_value="e@x.com", source="shopify"),
        CustomerIdentity(tenant_id=1, customer_id=ghost.id, identity_type="phone",
                         identity_value="+919876500001", source="klaviyo"),
    ])
    o1 = Order(tenant_id=1, customer_id=account.id, source="shopify", external_id="7001",
               order_number="MB-1", placed_at=datetime(2026, 1, 10), total_paise=100000)
    o2 = Order(tenant_id=1, customer_id=None, source="shopify", external_id="7002",
               order_number="MB-2", placed_at=datetime(2026, 3, 5), total_paise=50000)
    s.add_all([o1, o2])
    # guest PII lives only in the raw payload — resolve() reads it from there
    s.add(RawRecord(tenant_id=1, source="shopify", resource="orders", external_id="7002",
                    payload={"id": 7002, "customer": None, "phone": "9876500001",
                             "email": "E@X.com", "created_at": "2026-03-05T00:00:00Z"}))
    s.commit()
    return account, ghost, o1, o2


def test_guest_phone_order_plus_email_account_merge(session: Session) -> None:
    account, ghost, o1, o2 = _merge_fixture(session)

    report = resolve(session, tenant_id=1)

    assert isinstance(report, ResolveReport)
    assert report.customers_before == 2 and report.customers_after == 1
    assert report.merges == 1 and report.orders_attached == 1
    assert report.unresolved_orders == 0 and report.match_rate == 1.0

    # survivor = oldest (account has the earliest activity); absorbed never deleted
    ghost = session.get(Customer, ghost.id)
    assert ghost.merged_into_customer_id == account.id
    edge = session.scalars(select(IdentityEdge).filter_by(tenant_id=1)).one()
    assert (edge.survivor_id, edge.absorbed_id, edge.merge_key) == (
        account.id, ghost.id, "phone")

    # identities repointed, PII gaps filled on the survivor
    phone_identity = session.scalars(
        select(CustomerIdentity).filter_by(identity_type="phone",
                                           identity_value="+919876500001")).one()
    assert phone_identity.customer_id == account.id
    pii = session.get(CustomerPII, account.id)
    assert pii.primary_email == "e@x.com" and pii.primary_phone == "+919876500001"

    # history intact: both orders on one customer, sequenced correctly
    assert session.get(Order, o2.id).customer_id == account.id
    assert session.get(Order, o1.id).customer_order_index == 1
    assert session.get(Order, o2.id).customer_order_index == 2
    account = session.get(Customer, account.id)
    assert account.orders_count == 2 and account.total_spent_paise == 150000
    assert account.first_order_at == datetime(2026, 1, 10)

    # re-run = no-op
    again = resolve(session, tenant_id=1)
    assert again.merges == 0 and again.orders_attached == 0
    assert again.customers_before == 1 and again.customers_after == 1


def test_unmatched_guest_order_stays_unresolved(session: Session) -> None:
    session.add(Order(tenant_id=1, customer_id=None, source="shopify", external_id="8001",
                      order_number="MB-9", placed_at=datetime(2026, 4, 1), total_paise=10000))
    session.add(RawRecord(tenant_id=1, source="shopify", resource="orders", external_id="8001",
                          payload={"id": 8001, "customer": None, "phone": None,
                                   "email": "throwaway@x.com"}))
    session.commit()

    report = resolve(session, tenant_id=1)

    assert report.orders_attached == 0 and report.unresolved_orders == 1
    assert report.match_rate == 0.0
