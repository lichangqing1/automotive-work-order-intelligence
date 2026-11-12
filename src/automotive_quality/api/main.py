from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from automotive_quality.infrastructure.database.session import get_engine
from automotive_quality.shared.config import get_settings

from .auth import AuthenticatedPrincipal, get_bearer_authenticator
from .authorization import Permission
from .rate_limits import OperationCategory, enforce_rate_limit
from .v1 import router

Authenticated = Annotated[
    AuthenticatedPrincipal,
    Depends(enforce_rate_limit(Permission.READ, OperationCategory.READ)),
]

settings = get_settings()
if settings.environment.lower() in {"shared", "staging", "production"}:
    # Validate the complete credential structure before serving a shared deployment.
    get_bearer_authenticator()
app = FastAPI(title=settings.app_name, version="2.0.0", description="Data quality and AI-assisted test engineering platform")
app.include_router(router)


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def ready(
    response: Response,
    _principal: Authenticated,
) -> dict[str, str]:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ready", "database": "ok"}
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "database": "unavailable"}
