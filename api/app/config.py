from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

# Load environment files early so os.getenv picks them up (common when resolve_rpc_url falls back).
load_dotenv(".env")
load_dotenv(".env.local", override=True)


class ChainSettings(BaseModel):
    key: str
    display_name: str
    symbol: str
    chain_id: int
    rpc_env: str
    native_gas_limit: int = Field(default=21_000, ge=21_000)
    infura_network: str | None = None
    fee_model: str = Field(default="l1")
    price_symbol: str | None = None

    @property
    def env_var(self) -> str:
        return self.rpc_env


class AppSettings(BaseSettings):
    cache_ttl_seconds: int = Field(default=60, ge=5)
    chains_config_path: Path = Field(
        default=Path(__file__).resolve().parents[2] / "shared" / "chains.json"
    )
    http_timeout_seconds: float = Field(default=8.0, ge=1.0)
    http_max_connections: int = Field(default=12, ge=1)
    enable_precise_mode: bool = False
    estimate_from_address: str = Field(default="0x000000000000000000000000000000000000dead")
    estimate_to_address: str = Field(default="0x000000000000000000000000000000000000beef")
    estimate_value_wei: int = Field(default=1, ge=0)
    coinmarketcap_api_key: str | None = None
    price_cache_ttl_seconds: int = Field(default=300, ge=30)
    coinmarketcap_api_url: str = Field(
        default="https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    )

    model_config = {
        "env_file": ('.env.local', '.env'),
        "extra": "ignore",
    }

    def load_chains(self) -> List[ChainSettings]:
        raw = json.loads(self.chains_config_path.read_text(encoding="utf-8"))
        return [ChainSettings.model_validate(item) for item in raw]


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()


@lru_cache(maxsize=1)
def get_chains() -> list[ChainSettings]:
    settings = get_settings()
    return settings.load_chains()
