from __future__ import annotations

import os
from typing import Any, Dict, Iterable

import httpx

from ..config import ChainSettings


class RPCError(Exception):
    """Raised when an RPC call fails or returns an error payload."""


async def call_rpc(
    client: httpx.AsyncClient,
    url: str,
    method: str,
    params: Iterable[Any] | None = None,
) -> Dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": list(params or []),
    }
    response = await client.post(url, json=payload)
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        message = payload["error"].get("message", "unknown RPC error")
        raise RPCError(message)
    return payload


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
