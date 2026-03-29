from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.database import async_engine
from app.core.exceptions import AppException, app_exception_handler, http_exception_handler
from app.core.middleware import RequestIDMiddleware, SecurityHeadersMiddleware, TimingMiddleware
from app.core.redis import close_redis, get_redis, init_redis
from app.core.storage import ensure_bucket_exists, get_s3_client

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if settings.DEBUG else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    await init_redis()
    try:
        ensure_bucket_exists()
    except Exception as e:
        await logger.awarning("s3_init_failed", error=str(e))
    await logger.ainfo("app_started", app_name=settings.APP_NAME)

    yield

    # ── Shutdown ──
    await close_redis()
    await async_engine.dispose()
    await logger.ainfo("app_stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        lifespan=lifespan,
        docs_url="/api/v1/docs" if settings.DEBUG else None,
        redoc_url="/api/v1/redoc" if settings.DEBUG else None,
    )

    # ── Exception handlers ──
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)

    # ── Middleware (order matters: outermost first) ──
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(TimingMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Health endpoint ──
    @app.get(f"{settings.API_V1_PREFIX}/health")
    async def health_check():
        checks = {"db": False, "redis": False, "s3": False}
        try:
            async with async_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["db"] = True
        except Exception as e:
            await logger.awarning("health_db_failed", error=str(e))

        try:
            redis = get_redis()
            await redis.ping()
            checks["redis"] = True
        except Exception:
            pass

        try:
            client = get_s3_client()
            client.head_bucket(Bucket=settings.S3_BUCKET_NAME)
            checks["s3"] = True
        except Exception:
            pass

        all_healthy = all(checks.values())
        any_healthy = any(checks.values())
        status = "healthy" if all_healthy else ("degraded" if any_healthy else "unhealthy")
        return {"status": status, "checks": checks}

    return app


app = create_app()
