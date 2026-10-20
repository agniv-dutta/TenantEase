"""FastAPI application entrypoint for TenantEase Khata."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlmodel import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import clock
from app.api import ledger, maintenance, model, portfolio, reminders, tenants
from app.config import settings
from app.db import engine, init_db

logger = logging.getLogger(__name__)

app = FastAPI(title="TenantEase Khata", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Wrap HTTP errors in the consistent {"error": {...}} body."""
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        body = {"error": detail}
    else:
        body = {"error": {"code": "http_error", "message": str(detail)}}
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return validation errors in the consistent error body."""
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(part) for part in first.get("loc", []))
    message = first.get("msg", "Invalid request")
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "validation_error", "message": f"{loc}: {message}".strip(": ")}},
    )


@app.exception_handler(FileNotFoundError)
async def data_out_of_date_handler(request: Request, exc: FileNotFoundError) -> JSONResponse:
    """Data that does not cover the open cycle is a reseed, never a silent gap."""
    return JSONResponse(
        status_code=503,
        content={"error": {"code": "data_out_of_date", "message": str(exc)}},
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a consistent error body for unhandled exceptions."""
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": "Something went wrong. Check the server logs."}},
    )


@app.on_event("startup")
def on_startup() -> None:
    """Initialise the database and score the open cycle if a model exists."""
    init_db()
    _warn_on_stale_data()
    try:
        from app.ml.scoring import score_open_cycle

        with Session(engine) as session:
            n = score_open_cycle(session)
        if n:
            logger.info("Scored %d leases for the open cycle", n)
    except FileNotFoundError as exc:
        logger.warning("Startup scoring skipped: %s", exc)
    except Exception as exc:  # pragma: no cover - startup must not crash the API
        logger.warning("Startup scoring skipped: %s", exc)


def _warn_on_stale_data() -> None:
    """Log loudly when the database was not seeded for the demo clock."""
    from app.ml.scoring import current_cycle
    from app.models import Meta

    with Session(engine) as session:
        try:
            current_cycle(session)
        except FileNotFoundError as exc:
            logger.warning("%s", exc)
            return
        seeded = session.get(Meta, "demo_today")

    if seeded is None:
        logger.warning("The data was seeded before DEMO_TODAY was recorded; run `make seed`.")
    elif seeded.value != clock.today().isoformat():
        logger.warning(
            "The data was seeded for %s but DEMO_TODAY is %s; run `make seed`.",
            seeded.value,
            clock.today().isoformat(),
        )


@app.get("/api/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(ledger.router, prefix="/api", tags=["ledger"])
app.include_router(tenants.router, prefix="/api/tenants", tags=["tenants"])
app.include_router(reminders.router, prefix="/api/reminders", tags=["reminders"])
app.include_router(maintenance.router, prefix="/api/maintenance", tags=["maintenance"])
app.include_router(model.router, prefix="/api/model", tags=["model"])
