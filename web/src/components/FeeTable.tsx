import type { FeeRow } from '../types/api';

interface Props {
  rows: FeeRow[];
  renderMode?: (mode?: string) => string;
}

const defaultRenderMode = (mode?: string) => mode ?? 'unknown';

function FeeTable({ rows, renderMode = defaultRenderMode }: Props) {
  return (
    <table>
      <thead>
        <tr>
          <th>Chain</th>
          <th>Gas Price (Gwei)</th>
          <th>Gas Limit</th>
          <th>Native Fee</th>
          <th>LP解体ガス量</th>
          <th>LP解体ガス手数料</th>
          <th>Mode</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const key = row.chain.key;
          const lp = row.lp_breaker;

          const lpGasLimit =
            lp && lp.gas_limit !== undefined && lp.gas_limit !== null
              ? lp.gas_limit.toLocaleString()
              : '—';

          const lpFeeContent = (() => {
            if (!lp) {
              return '—';
            }
            if (lp.error) {
              return <span className="badge error">{lp.error}</span>;
            }
            if (!lp.native_fee) {
              return '—';
            }
            const parts = [`${lp.native_fee.formatted} ${row.chain.symbol}`];
            if (lp.fiat_fee) {
              parts.push(`(${lp.fiat_fee.formatted} ${lp.fiat_fee.currency})`);
            }
            return parts.join(' ');
          })();

          const statusBadges: JSX.Element[] = [];
          if (row.error) {
            statusBadges.push(
              <span className="badge error" key="row-error">
                {row.error}
              </span>
            );
          }
          if (!row.error && row.stale) {
            const text = row.notes ?? 'stale cache';
            statusBadges.push(
              <span className="badge" key="row-stale">
                {text}
              </span>
            );
          } else if (!row.error && row.notes) {
            statusBadges.push(
              <span className="badge" key="row-notes">
                {row.notes}
              </span>
            );
          }
          if (lp?.error) {
            statusBadges.push(
              <span className="badge error" key="lp-error">
                {lp.error}
              </span>
            );
          } else if (lp?.notes && !lp.native_fee) {
            statusBadges.push(
              <span className="badge" key="lp-notes">
                {lp.notes}
              </span>
            );
          }
          if (statusBadges.length === 0) {
            statusBadges.push(
              <span className="badge" key="ok">
                ok
              </span>
            );
          }

          return (
            <tr key={key}>
              <td>{row.chain.display_name}</td>
              <td>{row.gas_price ? `${row.gas_price.gwei} Gwei` : '—'}</td>
              <td>{row.gas_limit ?? '—'}</td>
              <td>
                {row.native_fee
                  ? `${row.native_fee.formatted} ${row.chain.symbol}`
                  : '—'}
              </td>
              <td>{lpGasLimit}</td>
              <td>{lpFeeContent}</td>
              <td>{renderMode(row.mode)}</td>
              <td>{statusBadges}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export default FeeTable;
