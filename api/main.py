from contextlib import asynccontextmanager
import logging
import shutil
from pathlib import Path

from fastapi import FastAPI, HTTPException
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

ROOT_DIR = Path(__file__).resolve().parents[1]
RESUME_DIR = Path(__file__).resolve().parent / "static" / "resume"
ASSETS_DIR = RESUME_DIR / "assets"
SYSTEM_DESIGN_SRC = ROOT_DIR / "system-design-linkvault.png"
SYSTEM_DESIGN_DST = ASSETS_DIR / "system-design-linkvault.png"


def create_app() -> FastAPI:
    setup_logging()
    logger = logging.getLogger(__name__)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Copy system design image into the static tree so StaticFiles can serve it
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        if SYSTEM_DESIGN_SRC.exists() and not SYSTEM_DESIGN_DST.exists():
            shutil.copy2(SYSTEM_DESIGN_SRC, SYSTEM_DESIGN_DST)
            logger.info("Copied system design image to static assets")
        elif not SYSTEM_DESIGN_SRC.exists():
            logger.warning(
                "system-design-linkvault.png not found at %s — diagram will not render",
                SYSTEM_DESIGN_SRC,
            )

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

    # ── /health ──────────────────────────────────────────────────────────────
    # Must be registered before include_router so /{shortcode} doesn't swallow it.
    @app.get("/health", include_in_schema=True, tags=["ops"])
    async def health_check():
        from cache import ping as redis_ping

        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
            db_status = "ok"
        except Exception as e:
            logger.exception("Health check DB error")
            db_status = f"error: {e}"

        redis_status = "ok" if await redis_ping() else "error"

        overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"
        return {
            "status": overall,
            "db": db_status,
            "cache": redis_status,
            "version": "0.1.0",
        }

    # ── shortcode router ──────────────────────────────────────────────────────
    app.include_router(router)

    # ── /resume static site ───────────────────────────────────────────────────
    @app.get("/resume", include_in_schema=False)
    async def resume_redirect():
        return RedirectResponse(url="/resume/")

    app.mount(
        "/resume",
        StaticFiles(directory=str(RESUME_DIR), html=True),
        name="resume",
    )

    return app


app = create_app()