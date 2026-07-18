"""Engine/session factory. Swap LENS_DB_URL to Postgres later; no code change (ADR-001)."""

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings

engine: Engine = create_engine(settings.db_url)


@event.listens_for(engine, "connect")
def _sqlite_fks(dbapi_conn, _record) -> None:  # noqa: ANN001
    if engine.dialect.name == "sqlite":
        dbapi_conn.execute("PRAGMA foreign_keys=ON")


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Session:
    return SessionLocal()


def init_db() -> None:
    """Create all tables and upsert the event dictionary. Idempotent."""
    from . import models
    from .events import EVENTS

    models.Base.metadata.create_all(engine)
    with SessionLocal() as session:
        existing = {name for (name,) in session.query(models.EventDefinition.event_name)}
        for ev in EVENTS.values():
            if ev.name not in existing:
                session.add(
                    models.EventDefinition(
                        event_name=ev.name,
                        category=ev.category,
                        description=ev.description,
                        required_properties=dict(ev.required_properties),
                        is_derived=ev.is_derived,
                    )
                )
        session.commit()
