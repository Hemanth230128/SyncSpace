from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import health

app = FastAPI(
    title="AI Chat Platform",
    description="AI Collaborative Chat Platform — Foundation API",
    version="0.1.0",
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
