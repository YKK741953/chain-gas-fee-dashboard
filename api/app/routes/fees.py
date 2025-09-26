from __future__ import annotations

import asyncio
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..config import get_chains, get_settings
from ..services.gas import get_chain_fee

router = APIRouter(prefix="/fees", tags=["fees"])

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


def _format_timestamp(value: int | None) -> str:
    if not value:
        return "—"
    return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")


templates.env.filters["datetime"] = _format_timestamp


@router.get("/")
async def list_fees(request: Request, precise: bool = False, format: str | None = None):
    settings = get_settings()
    chains = get_chains()
    client = request.app.state.http_client

    jobs = [get_chain_fee(client, chain, precise=precise) for chain in chains]
    results = await asyncio.gather(*jobs)

    meta = {
        "precise_requested": precise,
        "precise_enabled": settings.enable_precise_mode,
        "cache_ttl_seconds": settings.cache_ttl_seconds,
        "generated_at": int(time.time()),
    }

    wants_html = (
        format == "html"
        or "text/html" in request.headers.get("accept", "")
        or request.query_params.get("format") == "html"
    )

    if wants_html:
        return templates.TemplateResponse(
            request=request,
            name="fees.html",
            context={
                "request": request,
                "rows": results,
                "meta": meta,
            },
        )

    return {"meta": meta, "data": results}
