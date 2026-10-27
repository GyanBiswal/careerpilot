from fastapi import FastAPI

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered interview preparation platform.",
)


@app.get("/health", tags=["Health"])
def health_check() -> dict:
    """Lightweight liveness check. No database or external calls."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
    }