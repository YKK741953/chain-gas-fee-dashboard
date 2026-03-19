from __future__ import annotations

import time

from api.app.services.history_store import get_history_store
from api.app.services.relative_index import build_relative_index, maybe_store_relative_index_sample


def test_build_relative_index_returns_warming_up_with_few_samples():
    now = int(time.time())
    store = get_history_store()
    for offset in range(10):
        store.insert_gas_price("ethereum", now - offset * 600, 1_000_000_000 + offset, mode="standard")

    relative_index, status = build_relative_index("ethereum", 1_000_000_100)

    assert relative_index is None
    assert status == "warming_up"


def test_build_relative_index_returns_ranked_score():
    now = int(time.time())
    store = get_history_store()
    start = now - (80 * 600)
    for index in range(80):
        store.insert_gas_price(
            "ethereum",
            start + index * 600,
            (index + 1) * 1_000_000_000,
            mode="standard",
        )

    relative_index, status = build_relative_index("ethereum", 72 * 1_000_000_000)

    assert status == "ok"
    assert relative_index is not None
    assert relative_index["score"] == 9
    assert relative_index["samples"] == 80
    assert relative_index["basis"] == "gas_price_gwei"


def test_maybe_store_relative_index_sample_skips_invalid_rows():
    now = int(time.time())
    stored = maybe_store_relative_index_sample(
        {
            "chain": {"key": "ethereum"},
            "gas_price": {"wei": 0},
        },
        observed_at=now,
    )
    assert stored is False

    stored = maybe_store_relative_index_sample(
        {
            "chain": {"key": "ethereum"},
            "gas_price": {"wei": 1_000_000_000},
            "stale": True,
        },
        observed_at=now,
    )
    assert stored is False
