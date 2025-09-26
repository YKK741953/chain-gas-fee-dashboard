from __future__ import annotations

import math
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

import httpx
from cachetools import TTLCache

from ..config import ChainSettings, get_settings
from .rpc import RPCError, call_rpc, resolve_rpc_url

NANO = Decimal("1e9")
WEI = Decimal("1e18")


@dataclass(slots=True)
class FeeSnapshot:
    chain: ChainSettings
    gas_price_wei: int
    gas_limit: int
    native_fee_wei: int
    fetched_at: float
    mode: str
    notes: Optional[str] = None

    def as_payload(self) -> Dict[str, Any]:
        gas_price_gwei = Decimal(self.gas_price_wei) / NANO
        native_fee = Decimal(self.native_fee_wei) / WEI
        return {
            "chain": {
                "key": self.chain.key,
                "display_name": self.chain.display_name,
                "symbol": self.chain.symbol,
                "chain_id": self.chain.chain_id,
            },
            "gas_price": {
                "wei": self.gas_price_wei,
                "gwei": _format_decimal(gas_price_gwei, 4),
            },
            "gas_limit": self.gas_limit,
            "native_fee": {
                "wei": self.native_fee_wei,
                "formatted": _format_decimal(native_fee, 8),
            },
            "fetched_at": int(self.fetched_at),
            "mode": self.mode,
            "notes": self.notes,
        }


settings = get_settings()
_fee_cache: TTLCache[str, FeeSnapshot] = TTLCache(maxsize=64, ttl=settings.cache_ttl_seconds)


async def get_chain_fee(
    client: httpx.AsyncClient,
    chain: ChainSettings,
    precise: bool = False,
) -> Dict[str, Any]:
    cache_key = _cache_key(chain, precise)
    snapshot = _fee_cache.get(cache_key)
    if snapshot is not None:
        return snapshot.as_payload()

    try:
        url = resolve_rpc_url(chain)
    except RPCError as exc:
        return _error_payload(chain, f"missing RPC url: {exc}")

    try:
        gas_price_wei, mode, notes = await _fetch_gas_price(client, url, precise)
        gas_limit = chain.native_gas_limit
        native_fee_wei = gas_price_wei * gas_limit
    except RPCError as exc:
        return _error_payload(chain, str(exc))
    except httpx.HTTPError as exc:
        return _error_payload(chain, f"http error: {exc}")

    snapshot = FeeSnapshot(
        chain=chain,
        gas_price_wei=gas_price_wei,
        gas_limit=gas_limit,
        native_fee_wei=native_fee_wei,
        fetched_at=time.time(),
        mode=mode,
        notes=notes,
    )
    _fee_cache[cache_key] = snapshot
    return snapshot.as_payload()


async def _fetch_gas_price(
    client: httpx.AsyncClient,
    url: str,
    precise: bool,
) -> tuple[int, str, Optional[str]]:
    effective_precise = precise and settings.enable_precise_mode

    try:
        history = await call_rpc(
            client,
            url,
            "eth_feeHistory",
            params=[5, "latest", [50]],
        )
        base_fee_hex = history["result"]["baseFeePerGas"][-1]
        base_fee = int(base_fee_hex, 16)

        priority_resp = await call_rpc(client, url, "eth_maxPriorityFeePerGas")
        priority_fee = int(priority_resp["result"], 16)

        gas_price_wei = base_fee + priority_fee
        notes = "baseFee+priority"
        return gas_price_wei, "standard", notes
    except Exception as primary_error:  # broad to allow fallback
        try:
            fallback_resp = await call_rpc(client, url, "eth_gasPrice")
            gas_price_wei = int(fallback_resp["result"], 16)
            notes = f"fallback:eth_gasPrice ({primary_error.__class__.__name__})"
            mode = "precise-fallback" if effective_precise else "fallback"
            return gas_price_wei, mode, notes
        except Exception as fallback_error:
            raise RPCError(f"unable to fetch gas price: {fallback_error}")


def _cache_key(chain: ChainSettings, precise: bool) -> str:
    return f"{chain.key}:{int(precise and settings.enable_precise_mode)}"


def _error_payload(chain: ChainSettings, message: str) -> Dict[str, Any]:
    return {
        "chain": {
            "key": chain.key,
            "display_name": chain.display_name,
            "symbol": chain.symbol,
            "chain_id": chain.chain_id,
        },
        "error": message,
    }


def _format_decimal(value: Decimal, digits: int) -> str:
    quantize_exp = Decimal(1) / (Decimal(10) ** digits)
    quantized = value.quantize(quantize_exp, rounding=ROUND_HALF_UP)
    return format(quantized, f'.{digits}f')
