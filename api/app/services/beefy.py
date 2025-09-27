from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import httpx
from cachetools import TTLCache

from ..config import (
    BeefyVaultSettings,
    ChainSettings,
    get_beefy_vaults,
    get_chains,
    get_settings,
)
from .gas import get_chain_fee

NANO = Decimal("1e9")
WEI = Decimal("1e18")


@dataclass(slots=True)
class BeefyVaultSnapshot:
    vault: BeefyVaultSettings
    chain: ChainSettings
    gas_price_wei: int | None
    native_fee_wei: int | None
    mode: str | None
    notes: str | None
    error: str | None
    reference: dict[str, Any]
    fetched_at: float

    def as_payload(self) -> dict[str, Any]:
        chain_payload = {
            "key": self.chain.key,
            "display_name": self.chain.display_name,
            "symbol": self.chain.symbol,
            "chain_id": self.chain.chain_id,
        }
        price_symbol = (self.chain.price_symbol or self.chain.symbol or self.chain.display_name).upper()
        payload: dict[str, Any] = {
            "vault": _vault_payload(self.vault),
            "chain": chain_payload,
            "gas_limit": self.vault.withdraw_gas_limit,
            "mode": self.mode,
            "notes": self.notes,
            "error": self.error,
            "fetched_at": int(self.fetched_at),
            "reference": self.reference,
            "price_symbol": price_symbol,
        }

        if self.gas_price_wei is not None:
            gwei_value = Decimal(self.gas_price_wei) / NANO
            payload["gas_price"] = {
                "wei": self.gas_price_wei,
                "gwei": _format_decimal(gwei_value, 4),
            }
        else:
            payload["gas_price"] = None

        if self.native_fee_wei is not None:
            native_value = Decimal(self.native_fee_wei) / WEI
            payload["native_fee"] = {
                "wei": self.native_fee_wei,
                "formatted": _format_decimal(native_value, 8),
            }
        else:
            payload["native_fee"] = None

        return payload


_settings = get_settings()
_vault_cache: TTLCache[str, BeefyVaultSnapshot] = TTLCache(maxsize=32, ttl=_settings.cache_ttl_seconds)


def reset_beefy_cache() -> None:
    global _settings, _vault_cache
    _settings = get_settings()
    _vault_cache = TTLCache(maxsize=32, ttl=_settings.cache_ttl_seconds)


async def get_beefy_withdraw_fees(
    client: httpx.AsyncClient,
    *,
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    vaults = get_beefy_vaults()
    if not vaults:
        return []

    chain_index = {chain.key: chain for chain in get_chains()}
    rows: list[dict[str, Any]] = []

    for vault in vaults:
        cache_key = vault.key
        if force_refresh:
            _vault_cache.pop(cache_key, None)

        cached = _vault_cache.get(cache_key)
        if cached is not None:
            rows.append(cached.as_payload())
            continue

        chain = chain_index.get(vault.chain_key)
        if chain is None:
            rows.append(_missing_chain_payload(vault))
            continue

        data = await get_chain_fee(client, chain, precise=False, force_refresh=force_refresh)
        fetched_at = float(data.get("fetched_at") or time.time())
        mode = data.get("mode")
        chain_notes = data.get("notes")
        combined_notes = _combine_notes(vault.notes, chain_notes)
        reference = _reference_payload(vault)

        if data.get("error"):
            snapshot = BeefyVaultSnapshot(
                vault=vault,
                chain=chain,
                gas_price_wei=None,
                native_fee_wei=None,
                mode=mode,
                notes=combined_notes,
                error=str(data["error"]),
                reference=reference,
                fetched_at=fetched_at,
            )
            rows.append(snapshot.as_payload())
            _vault_cache[cache_key] = snapshot
            continue

        gas_price = _extract_gas_price(data)
        if gas_price is None:
            snapshot = BeefyVaultSnapshot(
                vault=vault,
                chain=chain,
                gas_price_wei=None,
                native_fee_wei=None,
                mode=mode,
                notes=_combine_notes(combined_notes, "gas price unavailable"),
                error=None,
                reference=reference,
                fetched_at=fetched_at,
            )
            rows.append(snapshot.as_payload())
            _vault_cache[cache_key] = snapshot
            continue

        native_fee = gas_price * vault.withdraw_gas_limit

        snapshot = BeefyVaultSnapshot(
            vault=vault,
            chain=chain,
            gas_price_wei=gas_price,
            native_fee_wei=native_fee,
            mode=mode,
            notes=combined_notes,
            error=None,
            reference=reference,
            fetched_at=fetched_at,
        )
        rows.append(snapshot.as_payload())
        _vault_cache[cache_key] = snapshot

    return rows


def _combine_notes(*notes: str | None) -> str | None:
    filtered = [note for note in notes if note]
    if not filtered:
        return None
    return ", ".join(filtered)


def _format_decimal(value: Decimal, digits: int) -> str:
    quantize_exp = Decimal(1) / (Decimal(10) ** digits)
    quantized = value.quantize(quantize_exp, rounding=ROUND_HALF_UP)
    return format(quantized, f".{digits}f")


def _reference_payload(vault: BeefyVaultSettings) -> dict[str, Any]:
    reference: dict[str, Any] = {
        "gas_used": vault.withdraw_gas_limit,
    }
    if vault.reference_observed_at:
        reference["observed_at"] = vault.reference_observed_at
    if vault.reference_tx:
        reference["tx_hash"] = vault.reference_tx
    return reference


def _vault_payload(vault: BeefyVaultSettings) -> dict[str, Any]:
    payload = {
        "key": vault.key,
        "display_name": vault.display_name,
    }
    if vault.platform:
        payload["platform"] = vault.platform
    if vault.token_pair:
        payload["token_pair"] = vault.token_pair
    if vault.strategy:
        payload["strategy"] = vault.strategy
    return payload


def _missing_chain_payload(vault: BeefyVaultSettings) -> dict[str, Any]:
    now = int(time.time())
    payload = {
        "vault": _vault_payload(vault),
        "chain": {
            "key": vault.chain_key,
            "display_name": vault.chain_key,
            "symbol": "",
            "chain_id": 0,
        },
        "gas_limit": vault.withdraw_gas_limit,
        "mode": None,
        "notes": vault.notes,
        "error": f"chain '{vault.chain_key}' is not configured",
        "fetched_at": now,
        "reference": _reference_payload(vault),
        "price_symbol": None,
        "gas_price": None,
        "native_fee": None,
    }
    return payload


def _extract_gas_price(data: dict[str, Any]) -> int | None:
    gas_price = data.get("gas_price")
    if not gas_price:
        return None
    value = gas_price.get("wei")
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    return None
