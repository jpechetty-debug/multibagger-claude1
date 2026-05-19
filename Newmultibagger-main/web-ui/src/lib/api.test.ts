import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  BackendRegimeStatusResponse,
  BackendStockRecord,
} from './contracts'
import {
  api,
  normalizeRegimeResponse,
  normalizeStockRecord,
} from './api'

const originalFetch = globalThis.fetch

function jsonResponse(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => payload,
  } as Response
}

describe('api contract normalization', () => {
  const fetchMock = vi.fn<typeof fetch>()

  beforeEach(() => {
    vi.unstubAllEnvs()
    fetchMock.mockReset()
    globalThis.fetch = fetchMock
  })

  afterAll(() => {
    globalThis.fetch = originalFetch
  })

  it('normalizes snake_case stock records for the dashboard', () => {
    const record: BackendStockRecord = {
      symbol: 'INFY.NS',
      company_name: 'Infosys',
      price: 1450.5,
      score: 92,
      sector: 'Technology',
      ret_1m: 8.4,
      conviction_score: 77,
      as_of_date: '2026-04-02',
    }

    expect(normalizeStockRecord(record)).toEqual(
      expect.objectContaining({
        symbol: 'INFY.NS',
        name: 'Infosys',
        price: 1450.5,
        changePct: 8.4,
        score: 92,
        action: 'BUY',
        sector: 'Technology',
        convictionScore: 77,
        asOfDate: '2026-04-02',
      }),
    )
  })

  it('normalizes legacy mixed-case stock records and keeps explicit ratings', () => {
    const record: BackendStockRecord = {
      Symbol: 'SBIN.NS',
      Price: 799,
      Score: 72,
      Sector: 'Financials',
      Rating: 'WATCH',
      Ret_1M: -1.2,
      Conviction_Score: 31,
      As_Of_Date: null,
    }

    expect(normalizeStockRecord(record)).toEqual(
      expect.objectContaining({
        symbol: 'SBIN.NS',
        name: 'SBIN.NS',
        price: 799,
        changePct: -1.2,
        score: 72,
        action: 'WATCH',
        sector: 'Financials',
        convictionScore: 31,
        asOfDate: null,
      }),
    )
  })

  it('normalizes regime payloads into the frontend contract', () => {
    const response: BackendRegimeStatusResponse = {
      regime: 'BULLISH',
      vix: 12.4,
      vix_threshold: 18,
      momentum_accel: 1.35,
      votes: { breadth: 'positive' },
      is_forced: true,
      details: { source: 'manual' },
      timestamp: '2026-04-03T09:30:00Z',
      stale: true,
    }

    expect(normalizeRegimeResponse(response)).toEqual({
      regime: 'BULLISH',
      vix: 12.4,
      vixThreshold: 18,
      momentumAccel: 1.35,
      votes: { breadth: 'positive' },
      isForced: true,
      details: { source: 'manual' },
      timestamp: '2026-04-03T09:30:00Z',
      stale: true,
    })
  })

  it('surfaces backend detail messages when stock fetches fail', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ detail: 'Screening service unavailable' }, 503),
    )

    await expect(api.getStocks()).rejects.toMatchObject(
      expect.objectContaining({
        name: 'ApiError',
        message: 'Screening service unavailable',
        status: 503,
      }),
    )
  })

  it('fetches and normalizes live stock payloads', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse([
        {
          symbol: 'TCS.NS',
          company_name: 'Tata Consultancy Services',
          score: 88,
          price: 4012.25,
          sector: 'Technology',
          ret_1m: 6.1,
          conviction_score: 68,
          as_of_date: '2026-04-02',
        },
      ]),
    )

    await expect(api.getStocks()).resolves.toEqual([
      expect.objectContaining({
        symbol: 'TCS.NS',
        name: 'Tata Consultancy Services',
        action: 'WATCH',
        convictionScore: 68,
      }),
    ])
    expect(fetchMock).toHaveBeenCalledWith('/api/stocks', expect.objectContaining({
      headers: { 'X-API-Key': 'DEV_KEY_123' },
    }))
  })

  it('attaches the configured API key header to backend requests', async () => {
    vi.stubEnv('VITE_SOVEREIGN_API_KEY', 'frontend-secret')
    fetchMock.mockResolvedValueOnce(jsonResponse([]))

    await api.getStocks()

    expect(fetchMock).toHaveBeenCalledWith('/api/stocks', expect.objectContaining({
      headers: { 'X-API-Key': 'frontend-secret' },
    }))
  })
})
