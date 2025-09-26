# Repository Guidelines

## Language
ユーザーへの返答は、日本語で返答すること。

## Project Structure & Module Organization
- `doc/` holds the requirement (`要件定義書.md`) and implementation plan (`実装計画書.md`); sync any scope or API change there first.
- `dailyreport/` is for dated work notes and operational findings; add one markdown per session.
- Keep FastAPI code in `api/app/` with domain subpackages (for example `chains`, `pricing`, `config`) and tests in `api/tests/`.
- The Vite + TypeScript client belongs in `web/`, separating UI components (`web/src/components/`), state (`web/src/state/`), and helpers (`web/src/lib/`). Static assets go to `web/public/`.

## Build, Test, and Development Commands
- Backend bootstrap: `python -m venv .venv && source .venv/bin/activate && pip install -r api/requirements.txt`.
- Start the API with `uvicorn api.app.main:app --reload`.
- Frontend bootstrap from `web/`: `npm install` (or `pnpm install` when a lockfile exists) then `npm run dev`.
- Use `docker compose up --build` after the compose file is committed to exercise `api`, `web`, and `nginx` together.

## Coding Style & Naming Conventions
- Python: 4-space indentation, type hints on public functions, `black` + `isort` for formatting, optional `mypy` before merges.
- TypeScript: ESLint + Prettier defaults, camelCase variables, PascalCase components, kebab-case files under `web/src/`. Prefix custom hooks with `use`.
- Centralize configuration in `.env.example`; never commit actual RPC URLs, API keys, or generated secrets.

## Testing Guidelines
- API tests stay in `api/tests/` and run via `pytest --asyncio-mode=auto --cov=api`, covering RPC success, fallbacks, and cache expiry.
- Frontend tests live beside components as `*.test.tsx`. Run them with `npm run test`, mocking API responses to assert each chain row renders.
- Before pushing run `pytest` and `npm run test`.

## Commit & Pull Request Guidelines
- Use imperative, scope-tagged commits such as `api: add gas cache` or `web: render fiat toggle`; squash fixups locally.
- PRs must include intent, functional summary, screenshots for UI changes, and links to issues or relevant daily reports.
- Highlight configuration changes (new env vars, cron jobs) and update both `README.md` and `.env.example` accordingly.

## Security & Configuration Tips
- Keep Infura and CoinGecko credentials in `.env.local` or Docker secrets and log required keys in `doc/`.
- Respect rate limits by polling ≥30 seconds and logging 429/timeouts to `dailyreport/`.
- Run `pip-audit` and `npm audit` before each release; note unresolved advisories in the release ticket with mitigation steps.
