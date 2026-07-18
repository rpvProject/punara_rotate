"""GET /v1/tenants/{id}/customers (pseudonymous list) and /{key} (PII detail)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..models import Tenant
from .deps import db_session, tenant
from .schemas import CustomerDetail, CustomersPage, Envelope

router = APIRouter(prefix="/v1", tags=["customers"])


@router.get("/tenants/{tenant_ref}/customers", response_model=CustomersPage)
def customers(
    t: Tenant = Depends(tenant),
    segment: str | None = Query(default=None, description="RFM segment label filter"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> dict:
    import lens.queries as queries

    return queries.customers_page(t.id, segment=segment, page=page, page_size=page_size)


@router.get(
    "/tenants/{tenant_ref}/customers/{customer_id}",
    response_model=Envelope[CustomerDetail],
)
def customer_detail(
    customer_id: int,
    t: Tenant = Depends(tenant),
    session: Session = Depends(db_session),
) -> dict:
    import lens.queries as queries

    detail = queries.customer_detail(session, t.id, customer_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="customer not found")
    return {"data": detail}
