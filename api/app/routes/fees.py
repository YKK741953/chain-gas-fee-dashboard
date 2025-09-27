from __future__ import annotations

import asyncio
import time
from datetime import datetime
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..config import ChainSettings, get_chains, get_settings
from ..services.beefy import get_beefy_withdraw_fees
from ..services.gas import get_chain_fee
from ..services.pricing import PricingError, get_price_quotes

router = APIRouter(prefix="/fees", tags=["fees"])

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


def _format_timestamp(value: int | None) -> str:
    if not value:
        return "—"
    return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")


templates.env.filters["datetime"] = _format_timestamp

_FIAT_FEE_DIGITS = {"USD": 4, "JPY": 2}
_FIAT_PRICE_DIGITS = {"USD": 2, "JPY": 0}
_WEI_DECIMAL = Decimal("1e18")
_DEFAULT_LP_GAS_LIMIT = 1_626_385


def _quantize(value: Decimal, digits: int) -> Decimal:
    quantize_exp = Decimal(1) / (Decimal(10) ** digits)
    return value.quantize(quantize_exp, rounding=ROUND_HALF_UP)


def _format_decimal_value(value: Decimal, digits: int) -> str:
    return format(_quantize(value, digits), f".{digits}f")


def _attach_fiat_prices(
    rows: list[dict[str, Any]],
    chains: list[ChainSettings],
    quotes: dict[str, Decimal],
    currency: str,
) -> None:
    if not quotes:
        return

    currency_upper = currency.upper()
    fee_digits = _FIAT_FEE_DIGITS.get(currency_upper, 2)
    price_digits = _FIAT_PRICE_DIGITS.get(currency_upper, 2)

    for row, chain in zip(rows, chains):
        native_fee = row.get("native_fee")
        if not native_fee:
            continue
        native_wei = native_fee.get("wei")
        if native_wei is None:
            continue
        symbol_key = (chain.price_symbol or chain.symbol or chain.display_name).upper()
        price = quotes.get(symbol_key)
        if price is None:
            continue
        native_amount = Decimal(native_wei) / _WEI_DECIMAL
        fiat_value = native_amount * price
        fiat_payload = {
            "currency": currency_upper,
            "value": float(fiat_value),
            "formatted": _format_decimal_value(fiat_value, fee_digits),
            "price_symbol": symbol_key,
        }
        row.setdefault("fiat_multi", {})[currency_upper] = fiat_payload
        if row.get("fiat_currency_active") == currency_upper:
            row["fiat_fee"] = fiat_payload

        price_payload = {
            "currency": currency_upper,
            "value": float(price),
            "formatted": _format_decimal_value(price, price_digits),
            "price_symbol": symbol_key,
        }
        row.setdefault("fiat_price_multi", {})[currency_upper] = price_payload
        if row.get("fiat_currency_active") == currency_upper:
            row["fiat_price"] = price_payload
        erc20 = row.get("erc20") or {}
        erc20_fee = erc20.get("fee", {})
        erc20_wei = erc20_fee.get("wei")
        if erc20_wei is None:
            if row.get("fiat_currency_active") == currency_upper:
                row["erc20_fiat_fee"] = None
        else:
            erc20_native_amount = Decimal(erc20_wei) / _WEI_DECIMAL
            erc20_fiat_value = erc20_native_amount * price
            erc20_payload = {
                "currency": currency_upper,
                "value": float(erc20_fiat_value),
                "formatted": _format_decimal_value(erc20_fiat_value, fee_digits),
                "price_symbol": symbol_key,
            }
            row.setdefault("erc20_fiat_multi", {})[currency_upper] = erc20_payload
            if row.get("fiat_currency_active") == currency_upper:
                row["erc20_fiat_fee"] = erc20_payload


def _attach_beefy_fiat_prices(
    rows: list[dict[str, Any]],
    quotes: dict[str, Decimal],
    currency: str,
) -> None:
    if not quotes:
        return

    currency_upper = currency.upper()
    fee_digits = _FIAT_FEE_DIGITS.get(currency_upper, 2)
    price_digits = _FIAT_PRICE_DIGITS.get(currency_upper, 2)

    for row in rows:
        native_fee = row.get("native_fee")
        price_symbol = (row.get("price_symbol") or "").upper()
        if not native_fee or not price_symbol:
            continue
        native_wei = native_fee.get("wei")
        if native_wei is None:
            continue
        price = quotes.get(price_symbol)
        if price is None:
            continue
        native_amount = Decimal(native_wei) / _WEI_DECIMAL
        fiat_value = native_amount * price
        payload = {
            "currency": currency_upper,
            "value": float(fiat_value),
            "formatted": _format_decimal_value(fiat_value, fee_digits),
            "price_symbol": price_symbol,
        }
        row.setdefault("fiat_multi", {})[currency_upper] = payload
        if row.get("fiat_currency_active") == currency_upper:
            row["fiat_fee"] = payload
        price_payload = {
            "currency": currency_upper,
            "value": float(price),
            "formatted": _format_decimal_value(price, price_digits),
            "price_symbol": price_symbol,
        }
        row.setdefault("fiat_price_multi", {})[currency_upper] = price_payload
        if row.get("fiat_currency_active") == currency_upper:
            row["fiat_price"] = price_payload


def _attach_lp_breaker_fiat(
    rows: list[dict[str, Any]],
    quotes: dict[str, Decimal],
    currency: str,
) -> None:
    if not quotes:
        return

    currency_upper = currency.upper()
    fee_digits = _FIAT_FEE_DIGITS.get(currency_upper, 2)
    price_digits = _FIAT_PRICE_DIGITS.get(currency_upper, 2)

    for row in rows:
        breaker = row.get("lp_breaker") or {}
        native_fee = breaker.get("native_fee")
        price_symbol = (breaker.get("price_symbol") or "").upper()
        if not native_fee or not price_symbol:
            continue
        native_wei = native_fee.get("wei")
        if native_wei is None:
            continue
        price = quotes.get(price_symbol)
        if price is None:
            continue
        native_amount = Decimal(native_wei) / _WEI_DECIMAL
        fiat_value = native_amount * price
        payload = {
            "currency": currency_upper,
            "value": float(fiat_value),
            "formatted": _format_decimal_value(fiat_value, fee_digits),
            "price_symbol": price_symbol,
        }
        breaker.setdefault("fiat_multi", {})[currency_upper] = payload
        if breaker.get("fiat_currency_active") == currency_upper:
            breaker["fiat_fee"] = payload
        price_payload = {
            "currency": currency_upper,
            "value": float(price),
            "formatted": _format_decimal_value(price, price_digits),
            "price_symbol": price_symbol,
        }
        breaker.setdefault("fiat_price_multi", {})[currency_upper] = price_payload
        if breaker.get("fiat_currency_active") == currency_upper:
            breaker["fiat_price"] = price_payload
        row["lp_breaker"] = breaker


@router.get("/")
async def list_fees(
    request: Request,
    precise: bool = False,
    format: str | None = None,
    fiat: str | None = None,
):
    settings = get_settings()
    chains = get_chains()
    client = request.app.state.http_client

    refresh_flag = request.query_params.get("refresh")
    force_refresh = False
    if refresh_flag is not None:
        force_refresh = refresh_flag.lower() in {"1", "true", "yes", "on"}

    jobs = [
        get_chain_fee(client, chain, precise=precise, force_refresh=force_refresh)
        for chain in chains
    ]
    results = await asyncio.gather(*jobs)
    _ensure_erc20_shape(results, chains)

    raw_fiat = fiat or request.query_params.get("fiat")
    fiat_currency = raw_fiat.lower() if raw_fiat else None

    wants_html = (
        format == "html"
        or "text/html" in request.headers.get("accept", "")
        or request.query_params.get("format") == "html"
    )

    beefy_rows = await get_beefy_withdraw_fees(client, force_refresh=force_refresh)
    beefy_map: dict[str, dict[str, Any]] = {}
    chain_settings_map = {chain.key: chain for chain in chains}

    for entry in beefy_rows:
        chain_info = entry.get("chain") or {}
        chain_key = chain_info.get("key")
        if chain_key and chain_key not in beefy_map:
            beefy_map[chain_key] = entry

    for row in results:
        chain = row.get("chain") or {}
        chain_key = chain.get("key")
        lp_entry = beefy_map.get(chain_key)
        gas_price_payload = row.get("gas_price") or {}
        gas_price_wei = gas_price_payload.get("wei")
        chain_settings = chain_settings_map.get(chain_key)
        price_symbol_value = None
        if chain_settings:
            price_symbol_value = (
                chain_settings.price_symbol or chain_settings.symbol or chain_settings.display_name
            )
        if not price_symbol_value:
            price_symbol_value = chain.get("symbol") or chain.get("display_name") or ""
        if lp_entry:
            row["lp_breaker"] = {
                "gas_limit": lp_entry.get("gas_limit"),
                "native_fee": lp_entry.get("native_fee"),
                "fiat_fee": lp_entry.get("fiat_fee"),
                "price_symbol": lp_entry.get("price_symbol"),
                "notes": lp_entry.get("notes"),
                "error": lp_entry.get("error"),
                "reference": lp_entry.get("reference"),
                "fetched_at": lp_entry.get("fetched_at"),
                "fiat_currency_active": None,
            }
        else:
            native_fee_payload = None
            notes = f"default CLM gas limit {_DEFAULT_LP_GAS_LIMIT:,}"
            if isinstance(gas_price_wei, int):
                native_fee_wei = gas_price_wei * _DEFAULT_LP_GAS_LIMIT
                native_amount = Decimal(native_fee_wei) / _WEI_DECIMAL
                native_fee_payload = {
                    "wei": native_fee_wei,
                    "formatted": _format_decimal_value(native_amount, 8),
                }
            else:
                notes = "gas price unavailable"

            row["lp_breaker"] = {
                "gas_limit": _DEFAULT_LP_GAS_LIMIT,
                "native_fee": native_fee_payload,
                "fiat_fee": None,
                "price_symbol": (price_symbol_value or "").upper(),
                "notes": notes,
                "error": None,
                "reference": {
                    "gas_used": _DEFAULT_LP_GAS_LIMIT,
                },
                "fetched_at": int(time.time()),
                "fiat_currency_active": None,
            }

    if wants_html and not fiat_currency:
        fiat_currency = "jpy"

    if fiat_currency and fiat_currency not in {"usd", "jpy"}:
        raise HTTPException(status_code=400, detail="Unsupported fiat currency")

    if beefy_rows:
        for entry in beefy_rows:
            entry.setdefault("fiat_fee", None)
            entry.setdefault("fiat_price", None)
            entry.setdefault("notes", None)
            entry.setdefault("error", None)

    meta = {
        "precise_requested": precise,
        "precise_enabled": settings.enable_precise_mode,
        "cache_ttl_seconds": settings.cache_ttl_seconds,
        "generated_at": int(time.time()),
        "refreshed": force_refresh,
    }

    fiat_sequences: list[tuple[str, bool]] = []
    if fiat_currency:
        fiat_sequences.append((fiat_currency, True))
    if wants_html:
        for currency in ("jpy", "usd"):
            if currency not in {item[0] for item in fiat_sequences}:
                fiat_sequences.append((currency, False))

    fiat_options: list[str] = []
    if fiat_sequences:
        price_symbols: set[str] = {
            (chain.price_symbol or chain.symbol or chain.display_name).upper()
            for chain in chains
        }
        price_symbols.update(
            (row.get("price_symbol") or "").upper()
            for row in beefy_rows
            if row.get("price_symbol")
        )
        price_symbols.update(
            (row.get("lp_breaker", {}).get("price_symbol") or "").upper()
            for row in results
            if row.get("lp_breaker")
        )
        price_symbols.discard("")

        for currency, mark_active in fiat_sequences:
            fiat_upper = currency.upper()
            fiat_options.append(fiat_upper)
            for row in results:
                row["fiat_currency_active"] = fiat_upper if mark_active else row.get(
                    "fiat_currency_active"
                )
                if row.get("lp_breaker"):
                    row["lp_breaker"]["fiat_currency_active"] = (
                        fiat_upper
                        if mark_active
                        else row["lp_breaker"].get("fiat_currency_active")
                    )

            try:
                quotes = await get_price_quotes(
                    client, sorted(price_symbols), currency, force_refresh=force_refresh
                )
            except PricingError as exc:
                meta["fiat_error"] = str(exc)
                break
            except httpx.HTTPError as exc:
                meta["fiat_error"] = f"fiat pricing failed ({exc.__class__.__name__})"
                break
            else:
                _attach_fiat_prices(results, chains, quotes, currency)
                if beefy_rows:
                    _attach_beefy_fiat_prices(beefy_rows, quotes, currency)
                _attach_lp_breaker_fiat(results, quotes, currency)
                if mark_active:
                    meta["fiat_currency"] = fiat_upper
                    meta["fiat_price_source"] = "coinmarketcap"
                    meta["fiat_requested"] = fiat_upper

    # Ensure active fiat fields align when no specific currency requested
    if not fiat_currency:
        for row in results:
            row["fiat_fee"] = None
            row["fiat_price"] = None
            row["erc20_fiat_fee"] = None
            if row.get("lp_breaker"):
                row["lp_breaker"]["fiat_fee"] = None

    if not fiat_options and wants_html:
        fiat_options = [meta.get("fiat_currency") or "JPY", "USD"]

    if wants_html:
        active_fiat = meta.get("fiat_currency") or meta.get("fiat_requested") or "JPY"
        return templates.TemplateResponse(
            request=request,
            name="fees.html",
            context={
                "request": request,
                "rows": results,
                "meta": meta,
                "fiat_currency": meta.get("fiat_currency"),
                "active_fiat": active_fiat,
                "force_refresh": force_refresh,
                "fiat_error": meta.get("fiat_error"),
                "fiat_options": fiat_options,
            },
        )

    for row in results:
        row.pop("fiat_currency_active", None)
        row.pop("fiat_price_multi", None)
        lp_data = row.get("lp_breaker")
        if lp_data:
            lp_data.pop("fiat_currency_active", None)
            lp_data.pop("fiat_price_multi", None)

    return {"meta": meta, "data": results}


@router.get("/beefy")
async def list_beefy_fees(
    request: Request,
    fiat: str | None = None,
):
    client = request.app.state.http_client

    refresh_flag = request.query_params.get("refresh")
    force_refresh = False
    if refresh_flag is not None:
        force_refresh = refresh_flag.lower() in {"1", "true", "yes", "on"}

    raw_fiat = fiat or request.query_params.get("fiat")
    fiat_currency = raw_fiat.lower() if raw_fiat else None
    if fiat_currency and fiat_currency not in {"usd", "jpy"}:
        raise HTTPException(status_code=400, detail="Unsupported fiat currency")

    rows = await get_beefy_withdraw_fees(client, force_refresh=force_refresh)
    for row in rows:
        row.setdefault("fiat_fee", None)
        row.setdefault("fiat_price", None)

    meta: dict[str, Any] = {
        "generated_at": int(time.time()),
        "refreshed": force_refresh,
        "count": len(rows),
    }

    if fiat_currency:
        fiat_upper = fiat_currency.upper()
        meta["fiat_requested"] = fiat_upper
        price_symbols = sorted(
            {
                (row.get("price_symbol") or "").upper()
                for row in rows
                if row.get("native_fee") and row.get("price_symbol")
            }
        )
        for row in rows:
            row["fiat_currency_active"] = fiat_upper
        try:
            quotes = await get_price_quotes(
                client,
                price_symbols,
                fiat_currency,
                force_refresh=force_refresh,
            )
        except PricingError as exc:
            meta["fiat_error"] = str(exc)
        except httpx.HTTPError as exc:
            meta["fiat_error"] = f"fiat pricing failed ({exc.__class__.__name__})"
        else:
            meta["fiat_currency"] = fiat_upper
            meta["fiat_price_source"] = "coinmarketcap"
            _attach_beefy_fiat_prices(rows, quotes, fiat_currency)

    for row in rows:
        row.pop("fiat_currency_active", None)
        row.pop("fiat_price_multi", None)

    return {"meta": meta, "data": rows}


def _ensure_erc20_shape(rows: list[dict[str, Any]], chains: list[ChainSettings]) -> None:
    for row, chain in zip(rows, chains):
        erc20 = row.get("erc20")
        gas_limit = chain.erc20_gas_limit
        if not erc20:
            erc20 = row["erc20"] = {
                "gas_limit": gas_limit,
                "token_symbol": chain.erc20_token_symbol,
                "fee": {"wei": None, "formatted": None},
            }
        else:
            erc20.setdefault("gas_limit", gas_limit)
            erc20.setdefault("token_symbol", chain.erc20_token_symbol)
            fee = erc20.get("fee")
            if fee is None:
                erc20["fee"] = {"wei": None, "formatted": None}
            else:
                fee.setdefault("wei", None)
                fee.setdefault("formatted", None)
        row.setdefault("erc20_fiat_fee", None)
