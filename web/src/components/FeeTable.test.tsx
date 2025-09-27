import { render, screen } from '@testing-library/react';
import FeeTable from './FeeTable';
import type { FeeRow } from '../types/api';

const sampleRows: FeeRow[] = [
  {
    chain: {
      key: 'ethereum',
      display_name: 'Ethereum Mainnet',
      symbol: 'ETH',
      chain_id: 1,
    },
    gas_price: {
      wei: 3_000_000_000,
      gwei: '3.0000',
    },
    gas_limit: 21000,
    native_fee: {
      wei: 63_000_000_000_000,
      formatted: '0.00006300',
    },
    mode: 'standard',
    notes: 'baseFee+priority',
    fiat_multi: {
      JPY: {
        currency: 'JPY',
        value: 1890,
        formatted: '1890',
        price_symbol: 'ETH',
      },
    },
    lp_breaker: {
      gas_limit: 1_626_385,
      native_fee: {
        wei: 4_879_155_000_000_000,
        formatted: '0.00487915',
      },
      fiat_fee: {
        currency: 'USD',
        value: 0.146,
        formatted: '0.1460',
        price_symbol: 'ETH',
      },
      fiat_multi: {
        USD: {
          currency: 'USD',
          value: 0.146,
          formatted: '0.1460',
          price_symbol: 'ETH',
        },
      },
      notes: 'beefy test note',
      reference: {
        gas_used: 1_626_385,
        observed_at: '2025-09-27',
      },
    },
  },
  {
    chain: {
      key: 'optimism',
      display_name: 'OP Mainnet',
      symbol: 'ETH',
      chain_id: 10,
    },
    error: 'missing RPC url',
  },
];

test('renders fee rows and error badges', () => {
  render(<FeeTable rows={sampleRows} />);

  expect(screen.getByText('Ethereum Mainnet')).toBeInTheDocument();
  expect(screen.getByText('3.0000 Gwei')).toBeInTheDocument();
  expect(screen.getByText('0.00006300 ETH')).toBeInTheDocument();
  expect(screen.getByText('baseFee+priority')).toBeInTheDocument();
  expect(screen.getByText('1,626,385')).toBeInTheDocument();
  expect(screen.getByText('0.00487915 ETH (0.1460 USD)')).toBeInTheDocument();

  expect(screen.getByText('OP Mainnet')).toBeInTheDocument();
  expect(screen.getByText('missing RPC url')).toHaveClass('badge');
});
