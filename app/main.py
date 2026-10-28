import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.routes import (
    analysis,
    applications,
    auth,
    checklist,
    job_descriptions,
    question_banks,
    resumes,
    users,
)
from app.core.config import get_settings
from app.db.session import get_db
from app.question_bank.loader import reload_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("careerpilot")

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Load question banks at startup; every problem is logged, none are silent.
    reload_store()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered interview preparation platform.",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(applications.router)
app.include_router(resumes.router)
app.include_router(job_descriptions.router)
app.include_router(analysis.router)
app.include_router(question_banks.router)
app.include_router(checklist.router)


@app.get("/health", tags=["Health"])
def health_check() -> dict:
    """Lightweight liveness check. No database or external calls."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
    }


@app.get("/health/db", tags=["Health"])
def database_health_check(db: Session = Depends(get_db)) -> dict:
    """Readiness check: confirms PostgreSQL is reachable."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Database health check failed")
        raise HTTPException(status_code=503, detail="Database unavailable")
    return {"status": "ok", "database": "connected"}