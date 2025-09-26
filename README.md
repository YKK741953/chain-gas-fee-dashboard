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

The frontend reads `VITE_API_BASE_URL`; if unset, it calls `/api` and relies on the proxy configuration.
