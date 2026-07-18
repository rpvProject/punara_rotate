"""Punara Lens v0 API — `lens api` serves this on 127.0.0.1:8010 (loopback only).

Error bodies carry BOTH shapes: `detail` (CONTRACTS.md §3 / FastAPI default,
what the frontend reads) and `error: {code, message}` (script consumers).
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import analytics, customers, health, scores, tenants

_ALLOWED_ORIGINS = ["http://127.0.0.1:3010", "http://localhost:3010"]

_CODES = {
    400: "bad_request",
    404: "not_found",
    405: "method_not_allowed",
    422: "validation_error",
    500: "internal_error",
}


def _error_body(status_code: int, message: str) -> dict:
    return {
        "detail": message,
        "error": {"code": _CODES.get(status_code, "http_error"), "message": message},
    }


def create_app() -> FastAPI:
    app = FastAPI(title="Punara Lens API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_ALLOWED_ORIGINS,
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    for module in (health, tenants, scores, analytics, customers):
        app.include_router(module.router)

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "error"
        return JSONResponse(status_code=exc.status_code, content=_error_body(exc.status_code, message))

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(_request: Request, exc: RequestValidationError) -> JSONResponse:
        message = (
            "; ".join(
                f"{'.'.join(str(part) for part in e['loc'])}: {e['msg']}" for e in exc.errors()
            )
            or "validation error"
        )
        return JSONResponse(status_code=422, content=_error_body(422, message))

    return app


app = create_app()
