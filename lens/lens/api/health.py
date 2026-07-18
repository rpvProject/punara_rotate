"""GET /v1/health — SQLite reachable + DuckDB file present."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from .deps import db_session
from .schemas import Envelope, Health

router = APIRouter(prefix="/v1", tags=["system"])


@router.get("/health", response_model=Envelope[Health])
def health(session: Session = Depends(db_session)) -> dict:
    try:
        session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    olap_ok = Path(settings.olap_path).exists()
    return {
        "data": {
            "status": "ok" if db_ok and olap_ok else "degraded",
            "db": db_ok,
            "olap": olap_ok,
        }
    }
