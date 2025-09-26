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
        row["fiat_fee"] = {
            "currency": currency_upper,
            "value": float(fiat_value),
            "formatted": _format_decimal_value(fiat_value, fee_digits),
            "price_symbol": symbol_key,
        }
        row["fiat_price"] = {
            "currency": currency_upper,
            "value": float(price),
            "formatted": _format_decimal_value(price, price_digits),
            "price_symbol": symbol_key,
        }


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

    if wants_html and not fiat_currency:
        fiat_currency = "jpy"

    if fiat_currency and fiat_currency not in {"usd", "jpy"}:
        raise HTTPException(status_code=400, detail="Unsupported fiat currency")

    meta = {
        "precise_requested": precise,
        "precise_enabled": settings.enable_precise_mode,
        "cache_ttl_seconds": settings.cache_ttl_seconds,
        "generated_at": int(time.time()),
        "refreshed": force_refresh,
    }

    if fiat_currency:
        fiat_upper = fiat_currency.upper()
        meta["fiat_requested"] = fiat_upper
        price_symbols = [
            (chain.price_symbol or chain.symbol or chain.display_name).upper()
            for chain in chains
        ]
        try:
            quotes = await get_price_quotes(
                client, price_symbols, fiat_currency, force_refresh=force_refresh
            )
        except PricingError as exc:
            meta["fiat_error"] = str(exc)
        except httpx.HTTPError as exc:
            meta["fiat_error"] = f"fiat pricing failed ({exc.__class__.__name__})"
        else:
            _attach_fiat_prices(results, chains, quotes, fiat_currency)
            meta["fiat_currency"] = fiat_upper
            meta["fiat_price_source"] = "coinmarketcap"

    if wants_html:
        active_fiat = meta.get("fiat_currency") or meta.get("fiat_requested")
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
            },
        )

    return {"meta": meta, "data": results}


def _ensure_erc20_shape(rows: list[dict[str, Any]], chains: list[ChainSettings]) -> None:
    for row, chain in zip(rows, chains):
        erc20 = row.get("erc20")
        gas_limit = chain.erc20_gas_limit
        if not erc20:
            row["erc20"] = {
                "gas_limit": gas_limit,
                "fee": {"wei": None, "formatted": None},
            }
            continue
        erc20.setdefault("gas_limit", gas_limit)
        erc20.setdefault("token_symbol", chain.erc20_token_symbol)
        fee = erc20.get("fee")
        if fee is None:
            erc20["fee"] = {"wei": None, "formatted": None}
        else:
            fee.setdefault("wei", None)
            fee.setdefault("formatted", None)
