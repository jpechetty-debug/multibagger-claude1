import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, beforeEach, vi } from 'vitest'

import App from './App'
import { api } from './lib/api'
import type { MarketRegimeData, SignalData } from './lib/contracts'

vi.mock('./components/metrics/Heartbeat', () => ({
  Heartbeat: () => <div data-testid="heartbeat-card">Heartbeat</div>,
}))

vi.mock('./lib/api', () => {
  const api = {
    getStocks: vi.fn(),
    getRegime: vi.fn(),
    getHealth: vi.fn(),
    getReport: vi.fn(),
  }

  return {
    api,
    ApiError: class ApiError extends Error {
      status: number

      constructor(message: string, status: number) {
        super(message)
        this.status = status
      }
    },
    getApiErrorMessage: (error: unknown) =>
      error instanceof Error && error.message
        ? error.message
        : 'Unable to reach the Sovereign backend.',
  }
})

const sampleRegime: MarketRegimeData = {
  regime: 'BULLISH',
  vix: 13.2,
  vixThreshold: 18,
  momentumAccel: 1.25,
  votes: { trend: 'up' },
  isForced: false,
  details: { source: 'model' },
  timestamp: '2026-04-03T10:00:00Z',
  stale: false,
}

const sampleSignals: SignalData[] = [
  {
    symbol: 'INFY.NS',
    name: 'Infosys',
    price: 1450.5,
    changePct: 8.4,
    score: 92,
    action: 'BUY',
    sector: 'Technology',
    convictionScore: 77,
    asOfDate: '2026-04-02',
    raw: { symbol: 'INFY.NS' },
  },
  {
    symbol: 'HDFCBANK.NS',
    name: 'HDFC Bank',
    price: 1682.1,
    changePct: 2.6,
    score: 84,
    action: 'WATCH',
    sector: 'Financials',
    convictionScore: 64,
    asOfDate: '2026-04-02',
    raw: { symbol: 'HDFCBANK.NS' },
  },
]

describe('App', () => {
  const getStocksMock = vi.mocked(api.getStocks)
  const getRegimeMock = vi.mocked(api.getRegime)
  const getHealthMock = vi.mocked(api.getHealth)

  beforeEach(() => {
    getStocksMock.mockReset()
    getRegimeMock.mockReset()
    getHealthMock.mockReset()
    getHealthMock.mockResolvedValue({
      status: 'ok',
      timestamp: '2026-04-03T10:00:00Z',
      latency_reference: 'stubbed',
    })
  })

  it('renders live signal data and regime metadata after a successful load', async () => {
    getStocksMock.mockResolvedValue(sampleSignals)
    getRegimeMock.mockResolvedValue(sampleRegime)

    render(<App />)

    expect(await screen.findByText('Infosys')).toBeInTheDocument()
    expect(screen.getByText('HDFC Bank')).toBeInTheDocument()
    expect(screen.getByText('BULLISH')).toBeInTheDocument()
    expect(screen.getByText('Showing 2/2 signals')).toBeInTheDocument()
    expect(screen.queryByText('Retry sync')).not.toBeInTheDocument()
  })

  it('shows an error banner and recovers after retrying', async () => {
    getStocksMock
      .mockRejectedValueOnce(new Error('Backend offline'))
      .mockResolvedValueOnce(sampleSignals)
    getRegimeMock.mockResolvedValue(sampleRegime)

    render(<App />)

    expect(await screen.findByText('Backend offline')).toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button', { name: /retry sync/i })[0])

    expect(await screen.findByText('Infosys')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.queryByText('Backend offline')).not.toBeInTheDocument()
    })
  })

  it('filters the signal grid and shows the empty-search state', async () => {
    getStocksMock.mockResolvedValue(sampleSignals)
    getRegimeMock.mockResolvedValue(sampleRegime)

    render(<App />)

    expect(await screen.findByText('Infosys')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Filter signal grid'), {
      target: { value: 'energy' },
    })

    expect(await screen.findByText('No matches for "energy"')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /clear/i }))

    await waitFor(() => {
      expect(screen.queryByText('No matches for "energy"')).not.toBeInTheDocument()
    })
    expect(screen.getByText('HDFC Bank')).toBeInTheDocument()
  })
})
