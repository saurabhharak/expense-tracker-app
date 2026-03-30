from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import text
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.database import async_engine
from app.core.exceptions import AppException, app_exception_handler, http_exception_handler
from app.core.middleware import RequestIDMiddleware, SecurityHeadersMiddleware, TimingMiddleware
from app.core.redis import close_redis, get_redis, init_redis
from app.core.storage import ensure_bucket_exists, get_s3_client

limiter = Limiter(key_func=get_remote_address)

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

    # ── Rate limiter state ──
    app.state.limiter = limiter

    # ── Exception handlers ──
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
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

    # ── Routers ──
    from app.auth.router import router as auth_router
    app.include_router(auth_router, prefix=settings.API_V1_PREFIX)

    # ── Health endpoint ──
    @app.get(f"{settings.API_V1_PREFIX}/health")
    @limiter.limit("60/minute")
    async def health_check(request: Request):
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
        if all_healthy:
            status, http_status = "healthy", 200
        elif any_healthy:
            status, http_status = "degraded", 207
        else:
            status, http_status = "unhealthy", 503
        return JSONResponse(status_code=http_status, content={"status": status, "checks": checks})

    return app


app = create_app()
