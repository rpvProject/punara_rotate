"""lens.seed tests — in-memory SQLite, foundation models only (no sibling seams)."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from lens import seed
from lens.models import Base, RawRecord

CUSTOMERS, MONTHS, SEED = 500, 24, 7


def _mem_session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _seed(session: Session) -> seed.SeedReport:
    return seed.run(session, "testbrand", months=MONTHS, seed=SEED, customers=CUSTOMERS)


@pytest.fixture(scope="module")
def universe() -> tuple[Session, seed.SeedReport]:
    session = _mem_session()
    return session, _seed(session)


def _raw(session: Session, source: str, resource: str) -> list[dict[str, Any]]:
    return [r.payload for r in session.scalars(
        select(RawRecord).where(RawRecord.source == source,
                                RawRecord.resource == resource))]


def _fingerprint(session: Session) -> str:
    rows = session.scalars(select(RawRecord)).all()
    blob = json.dumps(
        sorted((r.source, r.resource, r.external_id,
                json.dumps(r.payload, sort_keys=True)) for r in rows))
    return hashlib.sha256(blob.encode()).hexdigest()


def test_deterministic_across_fresh_databases(universe):
    session1, report1 = universe
    session2 = _mem_session()
    report2 = _seed(session2)
    assert report1.counts == report2.counts
    assert _fingerprint(session1) == _fingerprint(session2)


def test_rerun_is_noop(universe):
    session, first = universe
    total_before = len(session.scalars(select(RawRecord.id)).all())
    again = _seed(session)
    assert all(v == 0 for v in again.counts.values()), again.counts
    assert len(session.scalars(select(RawRecord.id)).all()) == total_before


def test_repeat_rate_in_range(universe):
    session, _ = universe
    orders = _raw(session, "shopify", "orders")
    per_person: Counter[str] = Counter()
    for o in orders:  # person key mirrors phone-first identity resolution
        key = o["phone"] or (o["email"] or "").lower() or (o["customer"] or {})["id"]
        per_person[key] += 1
    repeat = sum(1 for v in per_person.values() if v >= 2) / len(per_person)
    assert 0.20 <= repeat <= 0.40, repeat


def _walk_paise(node: Any, path: str = "") -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k.endswith("_paise") and v is not None:
                assert type(v) is int, f"{path}.{k}={v!r} is not int"
            _walk_paise(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk_paise(v, f"{path}[{i}]")


def test_money_is_integer_paise(universe):
    session, _ = universe
    for row in session.scalars(select(RawRecord)):
        _walk_paise(row.payload, f"{row.source}/{row.resource}/{row.external_id}")


def test_rto_only_on_shipments(universe):
    session, _ = universe
    orders = _raw(session, "shopify", "orders")
    assert all("rto" not in o for o in orders)  # orders never carry an rto flag
    shipments = _raw(session, "shiprocket", "shipments")
    rto = [s for s in shipments if s["rto"]]
    assert rto, "expected some RTO shipments"
    for s in rto:
        assert s["rto_at"] is not None
        assert s["delivered_at"] is None
        assert s["status"] == "rto_received"
    for s in shipments:
        if not s["rto"]:
            assert s["rto_at"] is None


def test_realism_bars(universe):
    session, report = universe
    assert report.counts["products"] == 60
    assert 120 <= report.counts["variants"] <= 240
    orders = _raw(session, "shopify", "orders")
    assert len(orders) >= CUSTOMERS  # every customer places at least one order
    cod = sum(o["cod"] for o in orders) / len(orders)
    assert 0.45 <= cod <= 0.65
    aov = sum(o["total_paise"] for o in orders) / len(orders)
    assert 80_000 <= aov <= 160_000  # ~Rs 1,100 with spread
    guest = sum(1 for o in orders if o["customer"] is None) / len(orders)
    assert guest > 0.02  # identity resolution has real work
    zero_priced = sum(1 for o in orders
                      if any(i["unit_price_paise"] == 0 for i in o["line_items"]))
    assert zero_priced > 0  # Signal Score raw material
