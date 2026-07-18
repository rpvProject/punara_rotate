"""GET /v1/tenants/{id}/{cohorts,rfm,revenue,leaks,...} — verbatim lens.queries reads.

Phase 2 (CONTRACTS V2.7) adds /predictions, /experiments, /cx, /messaging.
Their payloads are the exact dicts queries.py builds (pinned + tested there),
served through plain-dict envelopes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..models import Tenant
from .deps import db_session, tenant
from .schemas import CampaignRoiRow, Cohorts, Envelope, Leaks, RevenueMonth, Rfm

router = APIRouter(prefix="/v1", tags=["analytics"])


@router.get("/tenants/{tenant_ref}/cohorts", response_model=Envelope[Cohorts])
def cohorts(t: Tenant = Depends(tenant)) -> dict:
    import lens.queries as queries

    return {"data": queries.cohort_matrix(t.id)}


@router.get("/tenants/{tenant_ref}/rfm", response_model=Envelope[Rfm])
def rfm(t: Tenant = Depends(tenant)) -> dict:
    import lens.queries as queries

    return {"data": queries.rfm_grid(t.id)}


@router.get("/tenants/{tenant_ref}/revenue", response_model=Envelope[list[RevenueMonth]])
def revenue(t: Tenant = Depends(tenant)) -> dict:
    import lens.queries as queries

    return {"data": queries.revenue_monthly(t.id)}


@router.get("/tenants/{tenant_ref}/leaks", response_model=Envelope[Leaks])
def leaks(t: Tenant = Depends(tenant)) -> dict:
    import lens.queries as queries

    return {"data": queries.leaks_summary(t.id)}


@router.get("/tenants/{tenant_ref}/campaigns", response_model=Envelope[list[CampaignRoiRow]])
def campaigns(t: Tenant = Depends(tenant)) -> dict:
    import lens.queries as queries

    return {"data": queries.campaign_roi(t.id)}


# ------------------------------------------------------------- Phase 2 (V2.7)


@router.get("/tenants/{tenant_ref}/predictions", response_model=Envelope[dict])
def predictions(
    t: Tenant = Depends(tenant),
    session: Session = Depends(db_session),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> dict:
    import lens.queries as queries

    payload = queries.predictions_summary(session, t.id, page=page, page_size=page_size)
    if payload is None:
        raise HTTPException(status_code=404, detail="no predictions yet")
    return {"data": payload}


@router.get("/tenants/{tenant_ref}/experiments", response_model=Envelope[list[dict]])
def experiments(
    t: Tenant = Depends(tenant), session: Session = Depends(db_session)
) -> dict:
    import lens.queries as queries

    return {"data": queries.experiments_list(session, t.id)}


@router.get("/tenants/{tenant_ref}/cx", response_model=Envelope[list[dict]])
def cx(t: Tenant = Depends(tenant)) -> dict:
    import lens.queries as queries

    return {"data": queries.cx_summary(t.id)}


@router.get("/tenants/{tenant_ref}/messaging", response_model=Envelope[dict])
def messaging(t: Tenant = Depends(tenant)) -> dict:
    import lens.queries as queries

    return {"data": queries.messaging_summary(t.id)}
