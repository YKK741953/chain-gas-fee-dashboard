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

export interface FeeRow {
  chain: ChainInfo;
  gas_price?: GasPrice;
  gas_limit?: number;
  native_fee?: NativeFee;
  fetched_at?: number;
  mode?: string;
  notes?: string | null;
  error?: string;
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
