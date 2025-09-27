from __future__ import annotations

import json
from decimal import Decimal

import pytest
import respx
from httpx import Response


def build_client_headers():
    return {"accept": "application/json"}


def make_rpc_handler(chain_slug: str, base_fee_hex: str, priority_fee_hex: str):
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
            return Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload.get("id", 1),
                    "result": "0x3f4d11",
                },
            )
        raise AssertionError(f"Unexpected method {method} for {chain_slug}")

    return handler


@pytest.mark.asyncio
async def test_beefy_endpoint_returns_payload(client):
    with respx.mock(assert_all_called=False) as mock:
        mock.route(host="test").pass_through()
        mock.post("https://rpc.test/avax").mock(
            side_effect=make_rpc_handler("avax", "0x3b9aca00", "0x77359400")
        )

        response = await client.get("/fees/beefy", headers=build_client_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["count"] == 1
    row = payload["data"][0]
    assert row["vault"]["display_name"] == "BTC.b-WAVAX CLM Vault"
    assert row["gas_limit"] == 1_626_385
    gas_price_wei = row["gas_price"]["wei"]
    assert gas_price_wei == int(Decimal("3") * Decimal("1e9"))
    expected_native_fee = gas_price_wei * row["gas_limit"]
    assert row["native_fee"]["wei"] == expected_native_fee
    assert row["native_fee"]["formatted"].startswith("0.0048")
    assert row["mode"].startswith("l1:")
    assert row["fiat_fee"] is None


@pytest.mark.asyncio
async def test_beefy_endpoint_with_fiat(client):
    with respx.mock(assert_all_called=False) as mock:
        mock.route(host="test").pass_through()
        mock.post("https://rpc.test/avax").mock(
            side_effect=make_rpc_handler("avax", "0x3b9aca00", "0x77359400")
        )
        mock.get("https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest").mock(
            return_value=Response(
                200,
                json={
                    "data": {
                        "AVAX": {
                            "quote": {
                                "USD": {"price": 30.0},
                            }
                        }
                    }
                },
            )
        )

        response = await client.get("/fees/beefy?fiat=usd", headers=build_client_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["fiat_requested"] == "USD"
    row = payload["data"][0]
    assert row["fiat_fee"]["formatted"].startswith("0.14")
    assert row["fiat_fee"]["currency"] == "USD"
    assert row["fiat_price"]["formatted"] == "30.00"
