from __future__ import annotations

import json
from typing import Callable

import pytest
import respx
from httpx import Response


def build_client_headers():
    return {"accept": "application/json"}


def make_rpc_handler(chain_slug: str, base_fee_hex: str, priority_fee_hex: str) -> Callable:
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
                        "reward": [[priority_fee_hex], [priority_fee_hex]],
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
        if method in ("eth_estimateGas", "linea_estimateGas"):
            gas_hex = "0x5208"  # 21000
            if chain_slug == "arb":
                gas_hex = "0x6000"
            if chain_slug == "linea":
                gas_hex = "0x5300"
            return Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload.get("id", 1),
                    "result": gas_hex,
                },
            )
        if method == "eth_call":
            return Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload.get("id", 1),
                    "result": "0x0",
                },
            )
        raise AssertionError(f"Unexpected method {method} for {chain_slug}")

    return handler


@pytest.mark.asyncio
async def test_fees_endpoint_returns_payload(client):
    with respx.mock(assert_all_called=False) as mock:
        mock.route(host="test").pass_through()
        for slug in ("eth", "pol", "arb", "op", "avax", "linea"):
            mock.post(f"https://rpc.test/{slug}").mock(
                side_effect=make_rpc_handler(slug, "0x3b9aca00", "0x77359400")
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
    assert first["erc20"]["gas_limit"] == 55000
    assert first["erc20"]["fee"]["formatted"].startswith("0.000165")
    assert first["erc20"]["token_symbol"] == "WBTC"
    assert first["erc20_fiat_fee"] is None


@pytest.mark.asyncio
async def test_missing_env_returns_error(client, monkeypatch):
    monkeypatch.delenv("RPC_OPTIMISM_URL", raising=False)

    with respx.mock(assert_all_called=False) as mock:
        mock.route(host="test").pass_through()
        for slug in ("eth", "pol", "arb", "avax", "linea"):
            mock.post(f"https://rpc.test/{slug}").mock(
                side_effect=make_rpc_handler(slug, "0x3b9aca00", "0x77359400")
            )

        response = await client.get("/fees/", headers=build_client_headers())

    assert response.status_code == 200
    data = response.json()["data"]
    optimism_row = next(row for row in data if row["chain"]["key"] == "optimism")
    assert "error" in optimism_row


@pytest.mark.asyncio
async def test_fees_html_view(client):
    with respx.mock(assert_all_called=False) as mock:
        mock.route(host="test").pass_through()
        for slug in ("eth", "pol", "arb", "op", "avax", "linea"):
            mock.post(f"https://rpc.test/{slug}").mock(
                side_effect=make_rpc_handler(slug, "0x3b9aca00", "0x77359400")
            )

        mock.get("https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest").mock(
            return_value=Response(
                200,
                json={
                    "data": {
                        "ETH": {"quote": {"JPY": {"price": 300000.0}}},
                        "POL": {"quote": {"JPY": {"price": 120.0}}},
                        "AVAX": {"quote": {"JPY": {"price": 4500.0}}},
                    }
                },
            )
        )

        response = await client.get("/fees/?format=html", headers={"accept": "text/html"})

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Gas Fee Snapshot" in response.text
    assert "法定通貨: JPY" in response.text
    assert "toggle" in response.text


@pytest.mark.asyncio
async def test_stale_snapshot_returns_when_rpc_fails(client):
    from api.app.services import gas

    failure_active = False

    def avalanche_handler(request):
        nonlocal failure_active
        payload = json.loads(request.content.decode())
        method = payload.get("method")

        if not failure_active:
            return make_rpc_handler("avax", "0x3b9aca00", "0x77359400")(request)

        if method in ("eth_feeHistory", "eth_gasPrice"):
            return Response(429)

        return make_rpc_handler("avax", "0x3b9aca00", "0x77359400")(request)

    with respx.mock(assert_all_called=False) as mock:
        mock.route(host="test").pass_through()
        for slug in ("eth", "pol", "arb", "op", "linea"):
            mock.post(f"https://rpc.test/{slug}").mock(
                side_effect=make_rpc_handler(slug, "0x3b9aca00", "0x77359400")
            )

        mock.post("https://rpc.test/avax").mock(side_effect=avalanche_handler)

        first_response = await client.get("/fees/", headers=build_client_headers())

    assert first_response.status_code == 200

    gas._fee_cache.clear()
    failure_active = True

    with respx.mock(assert_all_called=False) as mock:
        mock.route(host="test").pass_through()
        for slug in ("eth", "pol", "arb", "op", "linea"):
            mock.post(f"https://rpc.test/{slug}").mock(
                side_effect=make_rpc_handler(slug, "0x3b9aca00", "0x77359400")
            )

        mock.post("https://rpc.test/avax").mock(side_effect=avalanche_handler)

        second = await client.get("/fees/", headers=build_client_headers())

    assert second.status_code == 200
    data = second.json()["data"]
    avax_row = next(row for row in data if row["chain"]["key"] == "avalanche")
    assert avax_row.get("stale") is True
    assert "stale cache" in avax_row.get("notes", "")
    assert "HTTPStatusError" in avax_row.get("notes", "")
    assert "error" not in avax_row
    debug_msg = avax_row.get("debug_error", "")
    assert "infura.io/v3" not in debug_msg
    assert "***" in debug_msg
    assert avax_row["erc20"]["gas_limit"] == 55000
    assert avax_row["erc20"]["token_symbol"] == "WBTC"
    assert avax_row["erc20_fiat_fee"] is None


@pytest.mark.asyncio
async def test_linea_estimate_gas_accepts_int_payload(client):
    def linea_handler(request):
        payload = json.loads(request.content.decode())
        method = payload.get("method")
        if method == "linea_estimateGas":
            return Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload.get("id", 1),
                    "result": 21000,
                },
            )
        if method == "eth_feeHistory":
            return Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload.get("id", 1),
                    "result": {
                        "baseFeePerGas": ["0x3b9aca00", "0x3b9aca00"],
                    },
                },
            )
        if method == "eth_maxPriorityFeePerGas":
            return Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload.get("id", 1),
                    "result": "0x77359400",
                },
            )
        if method == "eth_gasPrice":
            return Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload.get("id", 1),
                    "result": "0x3b9aca00",
                },
            )
        raise AssertionError(f"Unexpected method {method}")

    with respx.mock(assert_all_called=False) as mock:
        mock.route(host="test").pass_through()
        for slug in ("eth", "pol", "arb", "op", "avax"):
            mock.post(f"https://rpc.test/{slug}").mock(
                side_effect=make_rpc_handler(slug, "0x3b9aca00", "0x77359400")
            )
        mock.post("https://rpc.test/linea").mock(side_effect=linea_handler)

        response = await client.get("/fees/", headers=build_client_headers())

    assert response.status_code == 200
    data = response.json()["data"]
    linea_row = next(row for row in data if row["chain"]["key"] == "linea")
    assert linea_row["gas_limit"] == 21000
    assert linea_row["notes"] == "linea_estimateGas, feeHistory(p50)+maxPriority"
    assert linea_row["erc20"]["gas_limit"] == 55000
    assert linea_row["erc20"]["token_symbol"] == "WBTC"
    assert linea_row.get("erc20_fiat_fee") is None


@pytest.mark.asyncio
async def test_fees_endpoint_with_fiat_currency(client):
    pricing_response = {
        "data": {
            "ETH": {
                "quote": {
                    "USD": {"price": 2000.0},
                }
            },
            "POL": {
                "quote": {
                    "USD": {"price": 0.5},
                }
            },
            "AVAX": {
                "quote": {
                    "USD": {"price": 30.0},
                }
            },
        }
    }

    with respx.mock(assert_all_called=False) as mock:
        for slug in ("eth", "pol", "arb", "op", "avax", "linea"):
            mock.post(f"https://rpc.test/{slug}").mock(
                side_effect=make_rpc_handler(slug, "0x3b9aca00", "0x77359400")
            )

        mock.get("https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest").mock(
            return_value=Response(200, json=pricing_response)
        )

        response = await client.get("/fees/?fiat=usd", headers=build_client_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["fiat_currency"] == "USD"
    assert payload["meta"]["fiat_requested"] == "USD"
    ethereum_row = next(row for row in payload["data"] if row["chain"]["key"] == "ethereum")
    assert ethereum_row["fiat_fee"]["formatted"] == "0.1260"
    assert ethereum_row["erc20_fiat_fee"]["formatted"] == "0.3300"
    # Ensure fallback symbol uses ETH for arbitrum/optimism/linea
    arbitrum_row = next(row for row in payload["data"] if row["chain"]["key"] == "arbitrum")
    assert arbitrum_row["fiat_fee"]["price_symbol"] == "ETH"
