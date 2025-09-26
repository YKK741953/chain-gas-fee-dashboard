import { useMemo } from 'react';
import FeeTable from './components/FeeTable';
import { formatSince, formatTimestamp, formatMode } from './lib/format';
import { useFeeData } from './state/useFeeData';

const POLL_OPTIONS = [30_000, 60_000, 120_000];

function App() {
  const {
    data,
    meta,
    loading,
    error,
    precise,
    setPrecise,
    pollIntervalMs,
    setPollIntervalMs,
    refresh,
  } = useFeeData();

  const pollLabel = useMemo(() => `${pollIntervalMs / 1000}s`, [pollIntervalMs]);
  const preciseEnabled = meta?.precise_enabled ?? false;
  const lastUpdated = meta?.generated_at;

  return (
    <main>
      <header>
        <h1>Gas Fee Comparator</h1>
        <p>Real-time snapshot of native transfer costs across tracked EVM chains.</p>
      </header>

      <div className="status-row">
        <span>Cache TTL: {meta?.cache_ttl_seconds ?? '—'}s</span>
        <span>Precise mode: {preciseEnabled ? 'available' : 'disabled'}</span>
        <span>Last updated: {formatTimestamp(lastUpdated)} ({formatSince(lastUpdated)})</span>
      </div>

      <div className="control-row">
        <label>
          <input
            type="checkbox"
            checked={precise}
            onChange={(event) => setPrecise(event.target.checked)}
            disabled={!preciseEnabled}
          />{' '}
          Precise mode
        </label>
        <label>
          Polling interval:
          <select
            value={pollIntervalMs}
            onChange={(event) => setPollIntervalMs(Number(event.target.value))}
          >
            {POLL_OPTIONS.map((option) => (
              <option value={option} key={option}>
                {option / 1000}s
              </option>
            ))}
          </select>
        </label>
        <button onClick={() => refresh()} disabled={loading}>
          Refresh
        </button>
        {loading && <span className="loading">Loading…</span>}
      </div>

      {error && (
        <div className="badge error" role="alert">
          {error}
        </div>
      )}

      <div className="table-wrapper">
        <FeeTable rows={data} renderMode={formatMode} />
      </div>
    </main>
  );
}

export default App;
