from __future__ import annotations

from decimal import Decimal
from typing import Iterable

import httpx
from cachetools import TTLCache

from ..config import get_settings


class PricingError(Exception):
    """Raised when fetching fiat prices fails."""


_settings = get_settings()
_price_cache: TTLCache[tuple[str, tuple[str, ...]], dict[str, Decimal]] = TTLCache(
    maxsize=8, ttl=_settings.price_cache_ttl_seconds
)


async def get_price_quotes(
    client: httpx.AsyncClient,
    symbols: Iterable[str],
    currency: str,
    force_refresh: bool = False,
) -> dict[str, Decimal]:
    currency_upper = currency.upper()
    unique_symbols = sorted({symbol.upper() for symbol in symbols if symbol})
    if not unique_symbols:
        return {}

    cache_key = (currency_upper, tuple(unique_symbols))
    if force_refresh:
        _price_cache.pop(cache_key, None)
    else:
        cached = _price_cache.get(cache_key)
        if cached is not None:
            return cached

    settings = get_settings()
    api_key = settings.coinmarketcap_api_key
    if not api_key:
        raise PricingError("CoinMarketCap API key is not configured")

    params = {
        "symbol": ",".join(unique_symbols),
        "convert": currency_upper,
    }
    headers = {
        "X-CMC_PRO_API_KEY": api_key,
    }

    response = await client.get(settings.coinmarketcap_api_url, params=params, headers=headers)
    response.raise_for_status()

    payload = response.json()
    data = payload.get("data", {})
    quotes: dict[str, Decimal] = {}

    for symbol in unique_symbols:
        entry = data.get(symbol)
        if not entry:
            continue
        quote = entry.get("quote", {}).get(currency_upper)
        if not quote:
            continue
        price = quote.get("price")
        if price is None:
            continue
        quotes[symbol] = Decimal(str(price))

    if quotes:
        _price_cache[cache_key] = quotes

    return quotes
