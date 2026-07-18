"""Smallest checks that fail if the foundation breaks."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lens.events import EVENTS, event_id
from lens.models import Base, EventDefinition, Order, Tenant


def test_schema_creates_and_is_idempotent() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Base.metadata.create_all(engine)  # no-op second run
    with sessionmaker(bind=engine)() as s:
        t = Tenant(slug="t1", name="T1")
        s.add(t)
        s.flush()
        s.add(Order(tenant_id=t.id, source="shopify", external_id="o1",
                    placed_at=__import__("datetime").datetime(2026, 1, 1), total_paise=129900))
        s.commit()
        assert s.query(Order).one().total_paise == 129900  # integer paise


def test_event_dictionary() -> None:
    assert "order_placed" in EVENTS and "channel_opted_out" in EVENTS
    assert all(name == d.name for name, d in EVENTS.items())
    a = event_id(1, "shopify", "ord_1", "order_placed")
    assert a == event_id(1, "shopify", "ord_1", "order_placed")
    assert a != event_id(1, "shopify", "ord_1", "order_cancelled")
    assert len(a) == 64


def test_event_definitions_mirrorable() -> None:
    # every EventDef maps onto the EventDefinition table's columns
    for d in EVENTS.values():
        EventDefinition(event_name=d.name, category=d.category, description=d.description,
                        required_properties=dict(d.required_properties), is_derived=d.is_derived)
