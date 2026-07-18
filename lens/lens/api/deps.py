"""Shared FastAPI dependencies: per-request session, tenant resolution."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

from fastapi import Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Tenant


def db_session() -> Iterator[Session]:
    session = get_session()
    try:
        yield session
    finally:
        session.close()


def tenant(
    tenant_ref: str = Path(description="tenant id or slug"),
    session: Session = Depends(db_session),
) -> Tenant:
    """Resolve the {tenant_ref} path segment (numeric id or slug) to a Tenant, 404 unknown."""
    stmt = (
        select(Tenant).where(Tenant.id == int(tenant_ref))
        if tenant_ref.isdigit()
        else select(Tenant).where(Tenant.slug == tenant_ref)
    )
    found = session.execute(stmt).scalar_one_or_none()
    if found is None:
        raise HTTPException(status_code=404, detail="tenant not found")
    return found


def iso(dt: datetime | None) -> str | None:
    """Naive-UTC storage datetime -> contract ISO-8601 Z string."""
    return None if dt is None else dt.strftime("%Y-%m-%dT%H:%M:%SZ")
