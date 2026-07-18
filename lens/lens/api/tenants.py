"""GET /v1/tenants, /v1/tenants/{id}/overview, /v1/tenants/{id}/meta."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ScoreRun, SyncState, Tenant
from .deps import db_session, iso, tenant
from .schemas import Envelope, Meta, Overview, SourceFreshness, TenantOut

router = APIRouter(prefix="/v1", tags=["tenants"])


@router.get("/tenants", response_model=Envelope[list[TenantOut]])
def list_tenants(session: Session = Depends(db_session)) -> dict:
    rows = session.execute(select(Tenant).order_by(Tenant.id)).scalars().all()
    return {"data": rows}


@router.get("/tenants/{tenant_ref}/overview", response_model=Envelope[Overview])
def overview(t: Tenant = Depends(tenant)) -> dict:
    import lens.queries as queries

    return {"data": queries.overview_kpis(t.id)}


@router.get("/tenants/{tenant_ref}/meta", response_model=Envelope[Meta])
def meta(t: Tenant = Depends(tenant), session: Session = Depends(db_session)) -> dict:
    """Data freshness: last sync per source + last score run (08 §11)."""
    sync_rows = session.execute(
        select(SyncState.source, func.max(SyncState.last_synced_at))
        .where(SyncState.tenant_id == t.id)
        .group_by(SyncState.source)
        .order_by(SyncState.source)
    ).all()
    last_run = session.execute(
        select(ScoreRun)
        .where(ScoreRun.tenant_id == t.id)
        .order_by(ScoreRun.computed_at.desc(), ScoreRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    return {
        "data": {
            "tenant_id": t.id,
            "syncs": [
                SourceFreshness(source=source, last_synced_at=iso(last))
                for source, last in sync_rows
            ],
            "last_score_run_at": iso(last_run.computed_at) if last_run else None,
            "definition_version": last_run.definition_version if last_run else None,
        }
    }
