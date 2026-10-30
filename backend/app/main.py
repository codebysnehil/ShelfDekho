import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.config import get_settings
from app.db import analyst_engine, engine
from app.logging_config import configure_logging, request_id_var
from app.routers import analyst, core, dashboard, data, forecast

log = logging.getLogger("app.request")


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    yield
    await engine.dispose()
    if analyst_engine is not engine:
        await analyst_engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ShelfDekho API",
        version=__version__,
        description="Retail analytics, demand forecasting and an AI SQL analyst.",
        lifespan=lifespan,
    )

    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=settings.cors_origin_regex,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled error")
            response = JSONResponse({"detail": "Internal server error"}, status_code=500)
        finally:
            request_id_var.reset(token)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        response.headers["X-Request-ID"] = request_id
        log.info(
            "%s %s %s",
            request.method,
            request.url.path,
            response.status_code,
            extra={
                "fields": {
                    "request_id": request_id,
                    "status": response.status_code,
                    "ms": elapsed_ms,
                }
            },
        )
        return response

    app.include_router(core.router)
    app.include_router(core.meta)
    app.include_router(dashboard.router)
    app.include_router(forecast.router)
    app.include_router(analyst.router)
    app.include_router(data.router)
    return app


app = create_app()
