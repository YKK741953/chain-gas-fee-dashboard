# chain-gas-fee-dashboard

A lightweight dashboard that compares native transfer gas fees across Ethereum, Polygon PoS (POL), Arbitrum One, OP Mainnet, Avalanche C-Chain, and Linea. The project consists of a FastAPI backend that polls RPC endpoints and a Vite + React frontend that renders a comparison table.

## Prerequisites
- Python 3.11+
- Node.js 20+
- npm 10+ (or compatible package manager)

## Quick Start (local dev)
1. Copy `.env.example` to `.env.local`, set `INFURA_PROJECT_ID` (and optional secret), or provide full RPC URLs if using another provider.
2. Create a virtualenv and install backend deps:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r api/requirements.txt
   ```
3. Start the API:
   ```bash
   uvicorn api.app.main:app --reload --port 9000
   ```
4. Install frontend deps and start Vite (proxying `/api` → `http://localhost:9000`):
   ```bash
   cd web
   npm install
   npm run dev
   ```
5. Visit http://localhost:5173 to view the dashboard.

ブラウザから API を直接確認する場合は http://localhost:9000/fees/?format=html を開くとテーブル表示で参照できます。

## Tests
- Run backend tests with `pytest --asyncio-mode=auto --cov=api` (within the activated venv).
- Run frontend tests with `npm run test` from `web/`.

## Docker Compose
The included `docker-compose.yml` builds the API and an Nginx-served static frontend:
```bash
docker compose --env-file .env.local up --build
```
This exposes the API on `localhost:9000` and the dashboard on `localhost:8080`.

## Project Layout
- `api/` — FastAPI application, service modules, and tests.
- `web/` — Vite + React frontend client (TypeScript, Vitest).
- `shared/` — Chain metadata consumed by the API.
- `deploy/` — Container deployment assets (Nginx config).
- `doc/` — Japanese requirement/implementation artifacts.
- `dailyreport/` — Session notes (empty stub for now).
- `AGENTS.md` — contributor guidelines.

## Environment Variables
Backend configuration is loaded from `.env.local` (preferred) or `.env`:
- `CACHE_TTL_SECONDS`, `HTTP_TIMEOUT_SECONDS`, `HTTP_MAX_CONNECTIONS`, `ENABLE_PRECISE_MODE`
- `INFURA_PROJECT_ID` (and optionally `INFURA_PROJECT_SECRET`) to auto-generate Infura RPC URLs
- `RPC_<CHAIN>_URL` overrides for each tracked network when using non-Infura providers
- `ESTIMATE_FROM_ADDRESS` / `ESTIMATE_TO_ADDRESS` / `ESTIMATE_VALUE_WEI` で gas 推定時のトランザクション雛形を上書き可能
- `COINMARKETCAP_API_KEY` を設定すると `/fees?fiat=usd|jpy` 経由で法定通貨換算が有効化されます（TTL は `PRICE_CACHE_TTL_SECONDS`、エンドポイントは `COINMARKETCAP_API_URL` で調整可能）
- `FEE_HISTORY_REWARD_PERCENTILE` で EIP-1559 priority tip 推定に使用する reward percentile（MetaMask Medium=50）を切り替え可能

The frontend reads `VITE_API_BASE_URL`; if unset, it calls `/api` and relies on the proxy configuration.

## ガス計算ロジック
- Ethereum / Polygon / Avalanche: `eth_feeHistory` と `eth_maxPriorityFeePerGas` で EIP-1559 価格を構築し、`eth_estimateGas` による 21,000 gas と掛け合わせます。
- Optimism: `eth_estimateGas` と `eth_gasPrice` に加え、GasPriceOracle `getL1Fee` で L1 データ料を取得し合算します。
- Arbitrum: `eth_estimateGas` の結果に L1 バッファが含まれるため、`gasPrice * estimatedGas` が総コストです。
- Linea: `linea_estimateGas` が利用可能なら優先し、EIP-1559 価格で乗算します。
  HTML ビューではデフォルトで JPY 換算が有効になっており、トグルから USD / JPY を切り替えられます。API 側も `fiat=usd|jpy` 指定で CoinMarketCap 由来の法定通貨建て手数料を含みます。Native 送金と併せて ERC-20 送金時の推定ガス量／手数料も同テーブルに併記します。
