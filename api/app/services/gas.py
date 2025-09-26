from __future__ import annotations

import re
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlparse

import httpx
import rlp
from cachetools import TTLCache
from eth_abi import encode as abi_encode
from eth_utils import keccak, to_canonical_address

from ..config import ChainSettings, get_settings
from .rpc import RPCError, call_rpc, resolve_rpc_url

NANO = Decimal("1e9")
WEI = Decimal("1e18")
OP_GAS_ORACLE = "0x420000000000000000000000000000000000000F"
L1_FEE_SELECTOR = keccak(text="getL1Fee(bytes)")[:4].hex()


@dataclass(slots=True)
class FeeComputation:
    gas_price_wei: int
    gas_used: int
    native_fee_wei: int
    mode: str
    notes: Optional[str] = None
    l1_fee_wei: int = 0


@dataclass(slots=True)
class FeeSnapshot:
    chain: ChainSettings
    data: FeeComputation
    fetched_at: float

    def as_payload(self) -> Dict[str, Any]:
        gas_price_gwei = Decimal(self.data.gas_price_wei) / NANO
        native_fee = Decimal(self.data.native_fee_wei) / WEI
        erc20_fee_wei = self.data.gas_price_wei * self.chain.erc20_gas_limit
        if self.data.l1_fee_wei and self.data.gas_used:
            l1_component = (
                Decimal(self.data.l1_fee_wei)
                * Decimal(self.chain.erc20_gas_limit)
                / Decimal(self.data.gas_used)
            )
            erc20_fee_wei += int(l1_component.to_integral_value(rounding=ROUND_HALF_UP))
        erc20_fee_native = Decimal(erc20_fee_wei) / WEI
        return {
            "chain": {
                "key": self.chain.key,
                "display_name": self.chain.display_name,
                "symbol": self.chain.symbol,
                "chain_id": self.chain.chain_id,
            },
            "gas_price": {
                "wei": self.data.gas_price_wei,
                "gwei": _format_decimal(gas_price_gwei, 4),
            },
            "gas_limit": self.data.gas_used,
            "native_fee": {
                "wei": self.data.native_fee_wei,
                "formatted": _format_decimal(native_fee, 8),
            },
            "erc20": {
                "gas_limit": self.chain.erc20_gas_limit,
                "token_symbol": self.chain.erc20_token_symbol,
                "fee": {
                    "wei": erc20_fee_wei,
                    "formatted": _format_decimal(erc20_fee_native, 8),
                },
            },
            "fetched_at": int(self.fetched_at),
            "mode": self.data.mode,
            "notes": self.data.notes,
        }


settings = get_settings()
_fee_cache: TTLCache[str, FeeSnapshot] = TTLCache(maxsize=64, ttl=settings.cache_ttl_seconds)
_stale_cache: dict[str, FeeSnapshot] = {}


def reset_gas_cache() -> None:
    """Reset cached settings and fee cache (used in tests)."""
    global settings, _fee_cache
    settings = get_settings()
    _fee_cache = TTLCache(maxsize=64, ttl=settings.cache_ttl_seconds)
    _stale_cache.clear()


async def get_chain_fee(
    client: httpx.AsyncClient,
    chain: ChainSettings,
    precise: bool = False,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    cache_key = _cache_key(chain, precise)
    if force_refresh:
        _fee_cache.pop(cache_key, None)
    snapshot = _fee_cache.get(cache_key)
    if snapshot is not None:
        return snapshot.as_payload()

    stale_snapshot = _stale_cache.get(cache_key)

    try:
        computation = await _compute_fee(client, chain, precise)
    except (RPCError, httpx.HTTPError) as exc:
        if stale_snapshot is not None:
            payload = stale_snapshot.as_payload()
            payload["notes"] = _combine_notes(
                [payload.get("notes"), f"stale cache ({exc.__class__.__name__})"]
            )
            payload["stale"] = True
            payload["debug_error"] = _sanitize_error_message(str(exc))
            return payload
        return _error_payload(chain, str(exc))

    snapshot = FeeSnapshot(chain=chain, data=computation, fetched_at=time.time())
    _fee_cache[cache_key] = snapshot
    _stale_cache[cache_key] = snapshot
    return snapshot.as_payload()


async def _compute_fee(client: httpx.AsyncClient, chain: ChainSettings, precise: bool) -> FeeComputation:
    model = (chain.fee_model or "l1").lower()
    if model == "optimism":
        return await _compute_fee_optimism(client, chain)
    if model == "arbitrum":
        return await _compute_fee_arbitrum(client, chain)
    if model == "linea":
        return await _compute_fee_linea(client, chain)
    return await _compute_fee_l1(client, chain)


async def _compute_fee_l1(client: httpx.AsyncClient, chain: ChainSettings) -> FeeComputation:
    url = resolve_rpc_url(chain)
    tx = _build_tx_payload()
    gas_used, gas_note = await _estimate_gas(client, url, tx, fallback=chain.native_gas_limit)
    gas_price, price_note, price_mode = await _effective_gas_price(client, url)
    native_fee = gas_used * gas_price
    note = _combine_notes([gas_note, price_note])
    return FeeComputation(
        gas_price_wei=gas_price,
        gas_used=gas_used,
        native_fee_wei=native_fee,
        mode=f"l1:{price_mode}",
        notes=note,
        l1_fee_wei=0,
    )


async def _compute_fee_arbitrum(client: httpx.AsyncClient, chain: ChainSettings) -> FeeComputation:
    url = resolve_rpc_url(chain)
    tx = _build_tx_payload()
    gas_used, gas_note = await _estimate_gas(client, url, tx)
    gas_price, price_note, price_mode = await _effective_gas_price(client, url)
    native_fee = gas_used * gas_price
    note = _combine_notes(["estimateGas includes L1 buffer", gas_note, price_note])
    return FeeComputation(
        gas_price_wei=gas_price,
        gas_used=gas_used,
        native_fee_wei=native_fee,
        mode=f"arbitrum:{price_mode}",
        notes=note,
        l1_fee_wei=0,
    )


async def _compute_fee_optimism(client: httpx.AsyncClient, chain: ChainSettings) -> FeeComputation:
    url = resolve_rpc_url(chain)
    tx = _build_tx_payload()
    gas_used, gas_note = await _estimate_gas(client, url, tx)
    gas_price_resp = await call_rpc(client, url, "eth_gasPrice")
    gas_price = _hex_to_int(gas_price_resp["result"])
    price_note = "eth_gasPrice"
    l1_fee, l1_note = await _optimism_l1_fee(client, url, chain, tx, gas_price, gas_used)
    native_fee = gas_used * gas_price + l1_fee
    note = _combine_notes([gas_note, price_note, l1_note])
    return FeeComputation(
        gas_price_wei=gas_price,
        gas_used=gas_used,
        native_fee_wei=native_fee,
        mode="optimism:l2+l1",
        notes=note,
        l1_fee_wei=l1_fee,
    )


async def _compute_fee_linea(client: httpx.AsyncClient, chain: ChainSettings) -> FeeComputation:
    url = resolve_rpc_url(chain)
    tx = _build_tx_payload()
    try:
        gas_resp = await call_rpc(client, url, "linea_estimateGas", params=[tx])
        raw_result = gas_resp["result"]
        if isinstance(raw_result, dict) and "gasLimit" in raw_result:
            gas_used = _hex_to_int(raw_result["gasLimit"])
        else:
            gas_used = _hex_to_int(raw_result)
        gas_note = "linea_estimateGas"
    except Exception as exc:
        gas_used, gas_note = await _estimate_gas(client, url, tx, fallback=chain.native_gas_limit)
        gas_note = f"fallback estimateGas ({exc.__class__.__name__})"
    gas_price, price_note, price_mode = await _effective_gas_price(client, url)
    native_fee = gas_used * gas_price
    note = _combine_notes([gas_note, price_note])
    return FeeComputation(
        gas_price_wei=gas_price,
        gas_used=gas_used,
        native_fee_wei=native_fee,
        mode=f"linea:{price_mode}",
        notes=note,
        l1_fee_wei=0,
    )


async def _optimism_l1_fee(
    client: httpx.AsyncClient,
    url: str,
    chain: ChainSettings,
    tx: Dict[str, Any],
    gas_price: int,
    gas_limit: int,
) -> tuple[int, str]:
    raw_tx = _serialize_legacy_tx(chain, tx, gas_price, gas_limit)
    payload_bytes = abi_encode(["bytes"], [raw_tx])
    data = "0x" + L1_FEE_SELECTOR + payload_bytes.hex()
    call_params = {"to": OP_GAS_ORACLE, "data": data}
    try:
        fee_resp = await call_rpc(client, url, "eth_call", params=[call_params, "latest"])
        l1_fee = _hex_to_int(fee_resp["result"])
        return l1_fee, "GasPriceOracle.getL1Fee"
    except Exception as exc:
        return 0, f"optimism l1 fee fallback ({exc.__class__.__name__})"


async def _estimate_gas(
    client: httpx.AsyncClient,
    url: str,
    tx: Dict[str, Any],
    fallback: Optional[int] = None,
) -> tuple[int, Optional[str]]:
    try:
        resp = await call_rpc(client, url, "eth_estimateGas", params=[tx])
        return _hex_to_int(resp["result"]), "eth_estimateGas"
    except Exception as exc:
        if fallback is not None:
            return fallback, f"fallback:{exc.__class__.__name__}"
        raise RPCError(f"estimateGas failed: {exc}")


async def _effective_gas_price(
    client: httpx.AsyncClient,
    url: str,
) -> tuple[int, str, str]:
    try:
        reward_percentile = settings.fee_history_reward_percentile
        history = await call_rpc(
            client,
            url,
            "eth_feeHistory",
            params=[5, "latest", [reward_percentile]],
        )
        result = history["result"]
        base_fee_hex = result["baseFeePerGas"][-1]
        base_fee = _hex_to_int(base_fee_hex)
        priority_fee = None
        rewards = result.get("reward")
        if rewards:
            last_reward = rewards[-1]
            if last_reward:
                priority_fee = _hex_to_int(last_reward[0])
        note_suffix = f"feeHistory(p{reward_percentile})"
        if priority_fee is None:
            priority_resp = await call_rpc(client, url, "eth_maxPriorityFeePerGas")
            priority_fee = _hex_to_int(priority_resp["result"])
            return (
                base_fee + priority_fee,
                note_suffix + "+maxPriority",
                "eip1559",
            )
        return (
            base_fee + priority_fee,
            note_suffix,
            "eip1559",
        )
    except Exception as exc:
        fallback_resp = await call_rpc(client, url, "eth_gasPrice")
        gas_price = _hex_to_int(fallback_resp["result"])
        return gas_price, f"fallback gasPrice ({exc.__class__.__name__})", "legacy"


def _serialize_legacy_tx(chain: ChainSettings, tx: Dict[str, Any], gas_price: int, gas_limit: int) -> bytes:
    nonce = 0
    to_address = to_canonical_address(tx["to"])
    value = int(tx.get("value", "0x0"), 16)
    data_bytes = bytes.fromhex(tx.get("data", "0x")[2:])
    r = 0
    s = 0
    v = chain.chain_id
    return rlp.encode([nonce, gas_price, gas_limit, to_address, value, data_bytes, v, r, s])


def _build_tx_payload() -> Dict[str, Any]:
    value_hex = hex(settings.estimate_value_wei)
    return {
        "from": settings.estimate_from_address,
        "to": settings.estimate_to_address,
        "value": value_hex,
        "data": "0x",
    }


def _combine_notes(notes: Iterable[Optional[str]]) -> Optional[str]:
    filtered = [note for note in notes if note]
    if not filtered:
        return None
    return ", ".join(filtered)


def _cache_key(chain: ChainSettings, precise: bool) -> str:
    return f"{chain.key}:{chain.fee_model}:{int(precise and settings.enable_precise_mode)}"


def _error_payload(chain: ChainSettings, message: str) -> Dict[str, Any]:
    return {
        "chain": {
            "key": chain.key,
            "display_name": chain.display_name,
            "symbol": chain.symbol,
            "chain_id": chain.chain_id,
        },
        "error": message,
        "erc20": {
            "gas_limit": chain.erc20_gas_limit,
            "token_symbol": chain.erc20_token_symbol,
            "fee": {"wei": None, "formatted": None},
        },
    }


def _format_decimal(value: Decimal, digits: int) -> str:
    quantize_exp = Decimal(1) / (Decimal(10) ** digits)
    quantized = value.quantize(quantize_exp, rounding=ROUND_HALF_UP)
    return format(quantized, f".{digits}f")


def _hex_to_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    return int(value, 16)


_URL_PATTERN = re.compile(r"https?://[^\s'\"]+")


def _sanitize_error_message(message: str) -> str:
    def _mask(match: re.Match[str]) -> str:
        raw_url = match.group(0)
        parsed = urlparse(raw_url)
        if not parsed.scheme or not parsed.netloc:
            return "[redacted]"
        return f"{parsed.scheme}://{parsed.netloc}/***"

    return _URL_PATTERN.sub(_mask, message)
