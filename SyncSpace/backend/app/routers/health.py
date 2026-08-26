from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter(prefix="/api")


@router.get("/health")
async def health_check():
    """
    Basic API health check.

    Returns a simple JSON confirming the API is running.
    Does NOT check database connectivity — use /api/health/db for that.
    """
    return {
        "status": "healthy",
        "service": "AI Chat Platform API",
    }


@router.get("/health/db")
async def db_health_check(db: AsyncSession = Depends(get_db)):
    """
    Database health check.

    Runs `SELECT 1` against PostgreSQL to verify connectivity.
    Returns a clear status indicating success or failure with details.
    """
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()  # consume the result
        return {
            "status": "healthy",
            "database": "connected",
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "detail": str(e),
        }
