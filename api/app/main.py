from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx

from .config import get_settings
from .routes import fees, health

app = FastAPI(
    title="Chain Gas Fee API",
    version="0.1.0",
    description="Aggregates gas fees for configured EVM-compatible networks.",
)


@app.on_event("startup")
async def startup_event() -> None:
    settings = get_settings()
    limits = httpx.Limits(max_connections=settings.http_max_connections)
    timeout = httpx.Timeout(settings.http_timeout_seconds)
    app.state.http_client = httpx.AsyncClient(limits=limits, timeout=timeout)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    client: httpx.AsyncClient | None = getattr(app.state, "http_client", None)
    if client:
        await client.aclose()


settings = get_settings()
allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(fees.router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Chain Gas Fee API", "docs": "/docs"}
