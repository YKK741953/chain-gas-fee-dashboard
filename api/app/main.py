from __future__ import annotations

import asyncio
import logging
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx

from .config import get_settings
from .routes import fees, health
from .services.gas import get_chain_fee
from .services.history_store import get_history_store
from .services.relative_index import maybe_store_relative_index_sample

logger = logging.getLogger(__name__)

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
    get_history_store()
    if settings.relative_index_enabled and settings.relative_index_background_sampler_enabled:
        stop_event = asyncio.Event()
        app.state.relative_index_sampler_stop = stop_event
        app.state.relative_index_sampler_task = asyncio.create_task(
            _relative_index_sampler_loop(stop_event)
        )


@app.on_event("shutdown")
async def shutdown_event() -> None:
    stop_event: asyncio.Event | None = getattr(app.state, "relative_index_sampler_stop", None)
    sampler_task: asyncio.Task[None] | None = getattr(app.state, "relative_index_sampler_task", None)
    if stop_event is not None:
        stop_event.set()
    if sampler_task is not None:
        await sampler_task
    client: httpx.AsyncClient | None = getattr(app.state, "http_client", None)
    if client:
        await client.aclose()


async def _relative_index_sampler_loop(stop_event: asyncio.Event) -> None:
    settings = get_settings()
    while not stop_event.is_set():
        started_at = int(time.time())
        try:
            await _sample_relative_index_once(started_at)
        except Exception:
            logger.exception("relative index sampler failed")

        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=settings.relative_index_sample_interval_seconds,
            )
        except asyncio.TimeoutError:
            continue


async def _sample_relative_index_once(observed_at: int) -> None:
    client: httpx.AsyncClient = app.state.http_client
    settings = get_settings()
    chains = get_settings().load_chains()
    jobs = [get_chain_fee(client, chain, precise=False, force_refresh=True) for chain in chains]
    results = await asyncio.gather(*jobs)
    for row in results:
        maybe_store_relative_index_sample(row, observed_at=observed_at)

    retention_cutoff = observed_at - settings.relative_index_retention_days * 86400
    get_history_store().prune_before(retention_cutoff)


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
