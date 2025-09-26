import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { FeeRow, FeesResponse, FeesResponseMeta } from '../types/api';

const DEFAULT_POLL_MS = 60_000;
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api';

interface FeeDataState {
  data: FeeRow[];
  meta?: FeesResponseMeta;
  loading: boolean;
  error?: string;
  precise: boolean;
  pollIntervalMs: number;
  setPollIntervalMs: (next: number) => void;
  setPrecise: (next: boolean) => void;
  refresh: () => Promise<void>;
}

export function useFeeData(): FeeDataState {
  const [data, setData] = useState<FeeRow[]>([]);
  const [meta, setMeta] = useState<FeesResponseMeta | undefined>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | undefined>();
  const [precise, setPrecise] = useState(false);
  const [pollIntervalMs, setPollIntervalMs] = useState(DEFAULT_POLL_MS);
  const controllerRef = useRef<AbortController | null>(null);

  const fetchFees = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setError(undefined);

    try {
      const response = await fetch(
        `${API_BASE_URL}/fees/?precise=${precise ? 'true' : 'false'}`,
        { signal: controller.signal }
      );
      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }
      const payload = (await response.json()) as FeesResponse;
      setData(payload.data);
      setMeta(payload.meta);
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        return;
      }
      setError((err as Error).message);
      setData([]);
      setMeta(undefined);
    } finally {
      setLoading(false);
    }
  }, [precise]);

  useEffect(() => {
    fetchFees();
  }, [fetchFees]);

  useEffect(() => {
    const id = window.setInterval(fetchFees, pollIntervalMs);
    return () => window.clearInterval(id);
  }, [fetchFees, pollIntervalMs]);

  const refresh = useCallback(async () => {
    await fetchFees();
  }, [fetchFees]);

  const apiState = useMemo(
    () => ({
      data,
      meta,
      loading,
      error,
      precise,
      pollIntervalMs,
      setPollIntervalMs,
      setPrecise,
      refresh,
    }),
    [data, meta, loading, error, precise, pollIntervalMs, refresh]
  );

  return apiState;
}
