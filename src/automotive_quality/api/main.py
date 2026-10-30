from __future__ import annotations

from fastapi import FastAPI, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from automotive_quality.infrastructure.database.session import get_engine
from automotive_quality.shared.config import get_settings

from .v1 import router

settings = get_settings()
app = FastAPI(title=settings.app_name, version="2.0.0", description="Data quality and AI-assisted test engineering platform")
app.include_router(router)


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def ready(response: Response) -> dict[str, str]:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ready", "database": "ok"}
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "database": "unavailable"}
