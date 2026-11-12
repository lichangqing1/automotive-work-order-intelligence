from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from automotive_quality.infrastructure.database.session import get_engine
from automotive_quality.shared.config import get_settings
from automotive_quality.shared.security_logging import log_security_event

from .auth import AuthConfigurationError, AuthenticatedPrincipal, get_bearer_authenticator
from .authorization import Permission
from .rate_limits import OperationCategory, enforce_rate_limit
from .security import RequestBodyLimitMiddleware
from .v1 import router

Authenticated = Annotated[
    AuthenticatedPrincipal,
    Depends(enforce_rate_limit(Permission.READ, OperationCategory.READ)),
]

settings = get_settings()
if settings.environment.lower() in {"shared", "staging", "production"}:
    # Validate the complete credential structure before serving a shared deployment.
    try:
        get_bearer_authenticator()
    except AuthConfigurationError:
        log_security_event("deployment_configuration_failure", reason="invalid_authentication_configuration")
        raise
app = FastAPI(
    title=settings.app_name,
    version="2.0.0",
    description="Data quality and AI-assisted test engineering platform",
    docs_url="/docs" if settings.api_docs_enabled else None,
    redoc_url="/redoc" if settings.api_docs_enabled else None,
    openapi_url="/openapi.json" if settings.api_docs_enabled else None,
)
app.include_router(router)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.api_cors_allow_credentials,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
app.add_middleware(RequestBodyLimitMiddleware, max_bytes=settings.max_request_body_bytes)


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
