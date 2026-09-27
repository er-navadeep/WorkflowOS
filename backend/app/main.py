"""
WorkFlowOS — FastAPI Application
==================================
Bootstraps the FastAPI app, mounts all API routers, configures
logging, and wires up startup / shutdown lifecycle events.

Run from project root with:
    .venv\\Scripts\\python -m uvicorn app.main:app --reload --port 8000
    (must be run from inside the backend/ directory, or set PYTHONPATH)

Or use the helper script: scripts/start_backend.ps1
"""

from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Path bootstrap — ensure 'backend' is on sys.path so 'app.*' resolves
# ---------------------------------------------------------------------------
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..")
_backend_dir = os.path.normpath(_backend_dir)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# Load .env before any module reads env vars
load_dotenv()

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s - %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="WorkFlowOS API",
    description=(
        "AI-Powered OS-Level Workflow Automation.\n\n"
        "WorkFlowOS observes user activity, detects repeated workflows, "
        "generates automation proposals, and executes them after user approval."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ---------------------------------------------------------------------------
# CORS — allow the Vite dev server (port 5173) during development
# ---------------------------------------------------------------------------

ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Startup / shutdown hooks
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup() -> None:
    """Verify MongoDB connection and start trigger scheduler on startup."""
    from app.database.mongodb import check_database_connection
    from app.services.trigger_scheduler import start_trigger_scheduler

    try:
        check_database_connection()
        logger.info("MongoDB connection verified.")
    except Exception as exc:  # noqa: BLE001
        logger.critical("MongoDB connection FAILED: %s", exc)

    try:
        await start_trigger_scheduler()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not start trigger scheduler: %s", exc)


@app.on_event("shutdown")
async def shutdown() -> None:
    """Stop trigger scheduler cleanly on shutdown."""
    from app.services.trigger_scheduler import stop_trigger_scheduler

    try:
        await stop_trigger_scheduler()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error stopping trigger scheduler: %s", exc)

    logger.info("WorkFlowOS API shutting down.")


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

from app.api.events import router as events_router  # noqa: E402
from app.api.discovery import router as discovery_router  # noqa: E402
from app.api.understanding import router as understanding_router  # noqa: E402
from app.api.workflow_approval import router as workflow_approval_router  # noqa: E402
from app.api.workflows import router as workflows_router  # noqa: E402
from app.api.executions import router as executions_router  # noqa: E402
from app.api.triggers import router as triggers_router  # noqa: E402

API_PREFIX = "/api/v1"

app.include_router(events_router, prefix=API_PREFIX)
app.include_router(discovery_router, prefix=API_PREFIX)
app.include_router(understanding_router, prefix=API_PREFIX)
app.include_router(workflow_approval_router, prefix=API_PREFIX)
app.include_router(workflows_router, prefix=API_PREFIX)
app.include_router(executions_router, prefix=API_PREFIX)
app.include_router(triggers_router, prefix=API_PREFIX)



# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["System"], summary="Health check")
def health() -> dict:
    """Returns service status and MongoDB reachability."""
    from app.database.mongodb import check_database_connection

    db_ok = False
    try:
        db_ok = check_database_connection()
    except Exception:  # noqa: BLE001
        pass

    return {
        "status": "ok" if db_ok else "degraded",
        "service": "WorkFlowOS API",
        "version": "0.1.0",
        "database": "connected" if db_ok else "unreachable",
    }


# ---------------------------------------------------------------------------
# Root redirect to docs
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")
