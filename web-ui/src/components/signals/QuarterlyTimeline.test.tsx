import { render, screen } from '@testing-library/react'
import { describe, expect, it, beforeEach, vi } from 'vitest'
import QuarterlyTimeline from './QuarterlyTimeline'
import { api } from '../../lib/api'
import type { QuarterlyTimeline as QuarterlyTimelineType } from '../../lib/contracts'

vi.mock('../../lib/api', () => ({
  api: {
    getQuarterlyTimeline: vi.fn(),
  },
}))

// Mock recharts because it uses SVG and is hard to test in jsdom
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  ComposedChart: ({ children }: any) => <div>{children}</div>,
  LineChart: ({ children }: any) => <div>{children}</div>,
  Bar: () => <div />,
  Line: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Tooltip: () => <div />,
  Legend: () => <div />,
}))

const mockData: QuarterlyTimelineType = {
  symbol: 'TEST.NS',
  company_name: 'Test Corp',
  quarters: [
    {
      quarter: 'Q1 FY24',
      date: '2023-06-30',
      revenue: 1000,
      profit: 100,
      ebitda: 150,
      margin: 10,
      ebitda_margin: 15,
      revenue_growth_qoq: 5,
      profit_growth_qoq: 10,
      revenue_growth_yoy: 15,
      profit_growth_yoy: 20,
      eps: 10,
      book_value: 100
    }
  ],
  trends: {
    revenue_trend: 'GROWING',
    profit_trend: 'GROWING',
    margin_trend: 'EXPANDING',
    consistency: 'HIGH',
    avg_revenue_growth: 5,
    avg_profit_growth: 10,
    avg_margin: 10,
    quarters_with_growth: 1,
    total_quarters: 1
  },
  alerts: [
    {
      type: 'POSITIVE',
      message: 'Strong growth detected',
      severity: 'LOW'
    }
  ],
  timestamp: '2026-04-03T10:00:00Z'
}

describe('QuarterlyTimeline', () => {
  const getTimelineMock = vi.mocked(api.getQuarterlyTimeline)

  beforeEach(() => {
    getTimelineMock.mockReset()
  })

  it('renders loading state initially', () => {
    getTimelineMock.mockReturnValue(new Promise(() => {}))
    render(<QuarterlyTimeline symbol="TEST.NS" />)
    expect(screen.getByText(/RECONSTRUCTING FINANCIAL TIMELINE/i)).toBeInTheDocument()
  })

  it('renders data correctly after a successful fetch', async () => {
    getTimelineMock.mockResolvedValue(mockData)
    render(<QuarterlyTimeline symbol="TEST.NS" />)

    expect(await screen.findByText(/Strong growth detected/i)).toBeInTheDocument()
    expect(screen.getByText(/GROWING/i)).toBeInTheDocument()
    expect(screen.getByText(/Q1 FY24/i)).toBeInTheDocument()
    expect(screen.getByText(/1,000/i)).toBeInTheDocument() // Revenue
  })

  it('renders error state when fetch fails', async () => {
    getTimelineMock.mockRejectedValue(new Error('Backend Timeout'))
    render(<QuarterlyTimeline symbol="TEST.NS" />)

    expect(await screen.findByText(/DATA LINK SEVERED/i)).toBeInTheDocument()
    expect(screen.getByText(/Backend Timeout/i)).toBeInTheDocument()
  })
})
