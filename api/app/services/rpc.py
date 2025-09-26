from __future__ import annotations

import os
import asyncio
from typing import Any, Dict, Iterable

import httpx

from ..config import ChainSettings

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class RPCError(Exception):
    """Raised when an RPC call fails or returns an error payload."""


async def call_rpc(
    client: httpx.AsyncClient,
    url: str,
    method: str,
    params: Iterable[Any] | None = None,
    retries: int = 2,
    initial_backoff: float = 0.5,
) -> Dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": list(params or []),
    }
    attempt = 0
    backoff = initial_backoff
    while True:
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                message = data["error"].get("message", "unknown RPC error")
                raise RPCError(message)
            return data
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if attempt < retries and status in RETRYABLE_STATUS:
                await asyncio.sleep(backoff)
                attempt += 1
                backoff *= 2
                continue
            raise
        except httpx.RequestError:
            if attempt < retries:
                await asyncio.sleep(backoff)
                attempt += 1
                backoff *= 2
                continue
            raise


def resolve_rpc_url(chain: ChainSettings) -> str:
    env_value = os.getenv(chain.rpc_env)
    if env_value:
        return env_value

    project_id = os.getenv("INFURA_PROJECT_ID")
    if project_id and chain.infura_network:
        return f"https://{chain.infura_network}.infura.io/v3/{project_id}"

    raise RPCError(
        f"RPC endpoint missing. Set {chain.rpc_env} or INFURA_PROJECT_ID."
    )
