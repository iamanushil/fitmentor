import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from fitmentor.config import get_settings
from fitmentor.logging_config import configure_logging

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    log.info("app.startup", env=settings.app_env)
    yield
    log.info("app.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(title="FitMentor API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # tighten for prod
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    # Routers wired in as you build them (Days 3+)
    # from fitmentor.api.v1.router import api_router
    # app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
