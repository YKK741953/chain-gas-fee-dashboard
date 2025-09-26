from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
import httpx
from httpx import AsyncClient

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if not os.environ.get('ANYIO_BACKENDS'):
    os.environ['ANYIO_BACKENDS'] = 'asyncio'
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.app.main import app as fastapi_app
from api.app.services import gas
from api.app.services import rpc
from api.app.services import pricing


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    gas._fee_cache.clear()
    gas._stale_cache.clear()
    pricing._price_cache.clear()
    yield
    gas._fee_cache.clear()
    gas._stale_cache.clear()
    pricing._price_cache.clear()


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _sleep(_: float) -> None:
        return None

    monkeypatch.setattr(rpc.asyncio, "sleep", _sleep)


@pytest.fixture(autouse=True)
def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RPC_ETHEREUM_URL", "https://rpc.test/eth")
    monkeypatch.setenv("RPC_POLYGON_URL", "https://rpc.test/pol")
    monkeypatch.setenv("RPC_ARBITRUM_URL", "https://rpc.test/arb")
    monkeypatch.setenv("RPC_OPTIMISM_URL", "https://rpc.test/op")
    monkeypatch.setenv("RPC_AVALANCHE_URL", "https://rpc.test/avax")
    monkeypatch.setenv("RPC_LINEA_URL", "https://rpc.test/linea")
    monkeypatch.setenv("COINMARKETCAP_API_KEY", "test-key")
    monkeypatch.delenv("INFURA_PROJECT_ID", raising=False)
    monkeypatch.delenv("INFURA_PROJECT_SECRET", raising=False)


@pytest_asyncio.fixture()
async def client() -> AsyncIterator[AsyncClient]:
    http_client = httpx.AsyncClient()
    fastapi_app.state.http_client = http_client
    try:
        async with AsyncClient(app=fastapi_app, base_url="http://test") as client:
            yield client
    finally:
        await http_client.aclose()
        fastapi_app.state.__dict__.pop('http_client', None)
