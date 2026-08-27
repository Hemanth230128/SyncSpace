from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import auth, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager that handles startup and shutdown logic.
    On startup, it automatically creates database tables if they do not exist.
    """
    await init_db()
    yield


app = FastAPI(
    title="AI Chat Platform",
    description="AI Collaborative Chat Platform — Foundation & Auth API",
    version="0.2.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — allow the React dev server to make requests to this API
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(health.router)
app.include_router(auth.router)
