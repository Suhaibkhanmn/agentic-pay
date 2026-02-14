from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.rate_limit import limiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(debug=settings.DEBUG)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── Rate limiter ──
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ── CORS ──
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ──
    from app.api.v1 import (
        routes_auth,
        routes_dashboard,
        routes_vendors,
        routes_payments,
        routes_policies,
        routes_approvals,
        routes_audit,
    )

    prefix = settings.API_V1_PREFIX
    app.include_router(routes_auth.router, prefix=f"{prefix}/auth", tags=["Auth"])
    app.include_router(routes_dashboard.router, prefix=f"{prefix}/dashboard", tags=["Dashboard"])
    app.include_router(routes_vendors.router, prefix=f"{prefix}/vendors", tags=["Vendors"])
    app.include_router(routes_payments.router, prefix=f"{prefix}/payments", tags=["Payments"])
    app.include_router(routes_policies.router, prefix=f"{prefix}/policies", tags=["Policies"])
    app.include_router(routes_approvals.router, prefix=f"{prefix}/approvals", tags=["Approvals"])
    app.include_router(routes_audit.router, prefix=f"{prefix}/audit", tags=["Audit"])

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
