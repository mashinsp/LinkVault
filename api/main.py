from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from database import SessionLocal
from messaging import close_connection
from routers.links import limiter, router
from telemetry import setup_logging, setup_metrics, setup_tracing

# Set up structured logging first — before anything else logs
setup_logging()

logger = logging.getLogger(__name__)
ROOT_DIR = Path(__file__).resolve().parents[1]
RESUME_DIR = Path(__file__).resolve().parent / "static" / "resume"
SYSTEM_DESIGN_IMAGE = ROOT_DIR / "system-design-linkvault.png"


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("LinkVault API starting", extra={"env": "development"})
        yield
        await close_connection()
        logger.info("LinkVault API shutting down")

    app = FastAPI(
        title="LinkVault",
        description="Production-grade URL shortener",
        version="0.1.0",
        lifespan=lifespan,
    )

    setup_tracing(app)
    setup_metrics(app)

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    app.mount("/resume", StaticFiles(directory=str(RESUME_DIR), html=True), name="resume")
    return app


app = create_app()


@app.get("/resume", include_in_schema=False)
async def resume_root():
    return RedirectResponse(url="/resume/")


@app.get("/resume/assets/system-design-linkvault.png", include_in_schema=False)
async def resume_system_design():
    return FileResponse(str(SYSTEM_DESIGN_IMAGE))


@app.get("/health")
async def health_check():
    from cache import ping as redis_ping
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"

    redis_status = "ok" if await redis_ping() else "error"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "db": db_status,
        "cache": redis_status,
        "version": "0.1.0",
    }