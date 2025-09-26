from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Request

from ..config import get_chains, get_settings
from ..services.gas import get_chain_fee

router = APIRouter(prefix="/fees", tags=["fees"])


@router.get("/")
async def list_fees(request: Request, precise: bool = False) -> dict:
    settings = get_settings()
    chains = get_chains()
    client = request.app.state.http_client

    jobs = [get_chain_fee(client, chain, precise=precise) for chain in chains]
    results = await asyncio.gather(*jobs)

    return {
        "meta": {
            "precise_requested": precise,
            "precise_enabled": settings.enable_precise_mode,
            "cache_ttl_seconds": settings.cache_ttl_seconds,
            "generated_at": int(time.time()),
        },
        "data": results,
    }
