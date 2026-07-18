"""GET /v1/tenants/{id}/scores and /v1/tenants/{id}/scores/{name}/history."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..models import Tenant
from .deps import db_session, tenant
from .schemas import Envelope, ScoreHistoryPoint, ScoresLatest

router = APIRouter(prefix="/v1", tags=["scores"])

# CONTRACTS V2.7: all nine + ciq; ciq_partial history stays queryable.
VALID_SCORES = frozenset(
    {
        "gravity", "flow", "signal", "watertight",
        "vitals", "velocity", "autopilot", "pulse", "altitude",
        "ciq", "ciq_partial",
    }
)


@router.get("/tenants/{tenant_ref}/scores", response_model=Envelope[ScoresLatest])
def scores_latest(
    t: Tenant = Depends(tenant), session: Session = Depends(db_session)
) -> dict:
    import lens.queries as queries

    return {"data": queries.scores_latest(session, t.id)}


@router.get(
    "/tenants/{tenant_ref}/scores/{name}/history",
    response_model=Envelope[list[ScoreHistoryPoint]],
)
def score_history(
    name: str, t: Tenant = Depends(tenant), session: Session = Depends(db_session)
) -> dict:
    if name not in VALID_SCORES:
        raise HTTPException(status_code=404, detail="score not found")
    import lens.queries as queries

    return {"data": queries.score_history(session, t.id, name)}
