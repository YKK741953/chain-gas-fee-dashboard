export interface ChainInfo {
  key: string;
  display_name: string;
  symbol: string;
  chain_id: number;
}

export interface GasPrice {
  wei: number;
  gwei: string;
}

export interface NativeFee {
  wei: number;
  formatted: string;
}

export interface FiatValue {
  currency: string;
  value: number;
  formatted: string;
  price_symbol: string;
}

export interface FeeRow {
  chain: ChainInfo;
  gas_price?: GasPrice;
  gas_limit?: number;
  native_fee?: NativeFee;
  fetched_at?: number;
  mode?: string;
  notes?: string | null;
  error?: string;
  fiat_fee?: FiatValue | null;
  fiat_price?: FiatValue | null;
  erc20_fiat_fee?: FiatValue | null;
  stale?: boolean;
  lp_breaker?: LpBreakerInfo | null;
  fiat_multi?: Record<string, FiatValue | null>;
  fiat_price_multi?: Record<string, FiatValue | null>;
  erc20_fiat_multi?: Record<string, FiatValue | null>;
}

export interface FeesResponseMeta {
  precise_requested: boolean;
  precise_enabled: boolean;
  cache_ttl_seconds: number;
  generated_at: number;
}

export interface FeesResponse {
  meta: FeesResponseMeta;
  data: FeeRow[];
}

export interface BeefyVaultInfo {
  key: string;
  display_name: string;
  platform?: string;
  token_pair?: string;
  strategy?: string;
}

export interface BeefyReferenceInfo {
  gas_used: number;
  observed_at?: string;
  tx_hash?: string;
}

export interface BeefyFeeRow {
  vault: BeefyVaultInfo;
  chain: ChainInfo;
  gas_limit: number;
  gas_price?: GasPrice | null;
  native_fee?: NativeFee | null;
  fiat_fee?: FiatValue | null;
  fiat_price?: FiatValue | null;
  price_symbol?: string | null;
  notes?: string | null;
  error?: string | null;
  mode?: string | null;
  fetched_at?: number;
  reference?: BeefyReferenceInfo;
}

export interface LpBreakerInfo {
  gas_limit?: number | null;
  native_fee?: NativeFee | null;
  fiat_fee?: FiatValue | null;
  fiat_price?: FiatValue | null;
  price_symbol?: string | null;
  notes?: string | null;
  error?: string | null;
  reference?: BeefyReferenceInfo | null;
  fetched_at?: number;
  fiat_multi?: Record<string, FiatValue | null>;
  fiat_price_multi?: Record<string, FiatValue | null>;
}

export interface BeefyFeesMeta {
  generated_at: number;
  refreshed: boolean;
  count: number;
  fiat_requested?: string;
  fiat_currency?: string;
  fiat_price_source?: string;
  fiat_error?: string;
}

export interface BeefyFeesResponse {
  meta: BeefyFeesMeta;
  data: BeefyFeeRow[];
}
