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
          <th>Mode</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const key = row.chain.key;
          if (row.error) {
            return (
              <tr key={key}>
                <td>{row.chain.display_name}</td>
                <td colSpan={4}>—</td>
                <td>
                  <span className="badge error">{row.error}</span>
                </td>
              </tr>
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
              <td>{renderMode(row.mode)}</td>
              <td>
                {row.notes ? (
                  <span className="badge">{row.notes}</span>
                ) : (
                  <span className="badge">ok</span>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export default FeeTable;
