from __future__ import annotations

import json
from typing import Callable

import pytest
import respx
from httpx import Response


def build_client_headers():
    return {"accept": "application/json"}


def make_rpc_handler(base_fee_hex: str, priority_fee_hex: str) -> Callable:
    def handler(request):
        payload = json.loads(request.content.decode())
        method = payload.get("method")
        if method == "eth_feeHistory":
            return Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload.get("id", 1),
                    "result": {
                        "baseFeePerGas": [base_fee_hex, base_fee_hex],
                    },
                },
            )
        if method == "eth_maxPriorityFeePerGas":
            return Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload.get("id", 1),
                    "result": priority_fee_hex,
                },
            )
        if method == "eth_gasPrice":
            return Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload.get("id", 1),
                    "result": base_fee_hex,
                },
            )
        raise AssertionError(f"Unexpected method {method}")

    return handler


@pytest.mark.asyncio
async def test_fees_endpoint_returns_payload(client):
    with respx.mock(assert_all_called=False) as mock:
        for path in ("eth", "pol", "arb", "op", "avax", "linea"):
            mock.post(f"https://rpc.test/{path}").mock(
                side_effect=make_rpc_handler("0x3b9aca00", "0x77359400")
            )

        response = await client.get("/fees/", headers=build_client_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["precise_enabled"] is False
    data = payload["data"]
    assert len(data) == 6
    first = data[0]
    assert first["gas_price"]["gwei"] == "3.0000"
    assert first["native_fee"]["formatted"].startswith("0.000063")


@pytest.mark.asyncio
async def test_missing_env_returns_error(client, monkeypatch):
    monkeypatch.delenv("RPC_OPTIMISM_URL", raising=False)

    with respx.mock(assert_all_called=False) as mock:
        for path in ("eth", "pol", "arb", "avax", "linea"):
            mock.post(f"https://rpc.test/{path}").mock(
                side_effect=make_rpc_handler("0x3b9aca00", "0x77359400")
            )

        response = await client.get("/fees/", headers=build_client_headers())

    assert response.status_code == 200
    data = response.json()["data"]
    optimism_row = next(row for row in data if row["chain"]["key"] == "optimism")
    assert "error" in optimism_row


@pytest.mark.asyncio
async def test_fees_html_view(client):
    with respx.mock(assert_all_called=False) as mock:
        for path in ("eth", "pol", "arb", "op", "avax", "linea"):
            mock.post(f"https://rpc.test/{path}").mock(
                side_effect=make_rpc_handler("0x3b9aca00", "0x77359400")
            )

        response = await client.get("/fees/?format=html", headers={"accept": "text/html"})

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Gas Fee Snapshot" in response.text
