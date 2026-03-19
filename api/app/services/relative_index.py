from __future__ import annotations

import math
import time
from bisect import bisect_right
from typing import Any

from ..config import get_settings
from .history_store import get_history_store

_LABELS = {
    1: "かなり安い",
    2: "安い",
    3: "やや安い",
    4: "少し安い",
    5: "平常よりやや安い",
    6: "平常",
    7: "やや高い",
    8: "高い",
    9: "かなり高い",
    10: "極めて高い",
}


def build_relative_index(chain_key: str, current_gas_price_wei: int) -> tuple[dict[str, Any] | None, str]:
    settings = get_settings()
    if not settings.relative_index_enabled or current_gas_price_wei <= 0:
        return None, "disabled"

    now = int(time.time())
    since_ts = now - settings.relative_index_window_hours * 3600
    rows = get_history_store().fetch_gas_prices_since(chain_key, since_ts, mode="standard")
    values = sorted(gas_price_wei for _, gas_price_wei in rows if gas_price_wei > 0)
    sample_count = len(values)
    if sample_count < settings.relative_index_min_samples:
        if rows:
            oldest_ts = rows[0][0]
            if now - oldest_ts < settings.relative_index_warmup_hours * 3600:
                return None, "warming_up"
        return None, "insufficient_data"

    rank = bisect_right(values, current_gas_price_wei)
    percentile = rank / sample_count
    score = max(1, min(10, math.ceil(percentile * 10)))
    return (
        {
            "score": score,
            "scale_max": 10,
            "label": _LABELS[score],
            "percentile": round(percentile, 4),
            "window": "7d",
            "samples": sample_count,
            "basis": "gas_price_gwei",
        },
        "ok",
    )


def maybe_store_relative_index_sample(
    row: dict[str, Any],
    observed_at: int | None = None,
) -> bool:
    settings = get_settings()
    if not settings.relative_index_enabled:
        return False
    if row.get("error") or row.get("stale"):
        return False

    chain = row.get("chain") or {}
    chain_key = chain.get("key")
    gas_price = row.get("gas_price") or {}
    gas_price_wei = gas_price.get("wei")

    if not chain_key or not isinstance(gas_price_wei, int) or gas_price_wei <= 0:
        return False

    observed_at = observed_at or int(time.time())
    store = get_history_store()
    last_observed_at = store.latest_observed_at(chain_key, mode="standard")
    if (
        last_observed_at is not None
        and observed_at - last_observed_at < settings.relative_index_sample_interval_seconds
    ):
        return False

    store.insert_gas_price(chain_key, observed_at, gas_price_wei, mode="standard")
    return True
