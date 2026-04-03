import {
  type BackendRegimeStatusResponse,
  type BackendStockRecord,
  type HealthResponse,
  type MarkdownReportResponse,
  type MarketRegimeData,
  type SignalAction,
  type SignalData,
} from './contracts'

const BASE_URL = ''

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback
}

function readErrorMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === 'object') {
    const detail = (payload as { detail?: unknown }).detail
    const error = (payload as { error?: unknown }).error
    if (typeof detail === 'string' && detail.trim()) {
      return detail
    }
    if (typeof error === 'string' && error.trim()) {
      return error
    }
  }
  return fallback
}

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`)
  const contentType = response.headers.get('content-type') ?? ''
  const payload = contentType.includes('application/json')
    ? await response.json()
    : null

  if (!response.ok) {
    throw new ApiError(
      readErrorMessage(payload, `Request failed for ${path}`),
      response.status,
    )
  }

  return payload as T
}

function normalizeAction(rating: unknown, score: number): SignalAction {
  const normalizedRating = asString(rating).toUpperCase()
  if (
    normalizedRating === 'BUY' ||
    normalizedRating === 'WATCH' ||
    normalizedRating === 'REJECT' ||
    normalizedRating === 'DISQUALIFIED'
  ) {
    return normalizedRating
  }

  if (score >= 90) return 'BUY'
  if (score >= 75) return 'WATCH'
  if (score >= 50) return 'REJECT'
  return 'DISQUALIFIED'
}

export function normalizeStockRecord(record: BackendStockRecord): SignalData {
  const symbol = asString(record.symbol ?? record.Symbol, 'UNKNOWN')
  const score = asNumber(record.score ?? record.Score)
  const name = asString(record.name ?? record.company_name, symbol)
  const sector = asString(record.sector ?? record.Sector, 'Unknown')
  const price = asNumber(record.price ?? record.Price)
  const changePct = asNumber(record.ret_1m ?? record.Ret_1M)
  const convictionScore = asNumber(
    record.conviction_score ?? record.Conviction_Score,
  )
  const asOfDate = asString(record.as_of_date ?? record.As_Of_Date, '') || null

  return {
    symbol,
    name,
    price,
    changePct,
    score,
    action: normalizeAction(record.rating ?? record.Rating, score),
    sector,
    convictionScore,
    asOfDate,
    raw: record,
  }
}

export function normalizeRegimeResponse(
  response: BackendRegimeStatusResponse,
): MarketRegimeData {
  return {
    regime: asString(response.regime, 'UNKNOWN'),
    vix: asNumber(response.vix),
    vixThreshold: asNumber(response.vix_threshold),
    momentumAccel: asNumber(response.momentum_accel),
    votes: response.votes ?? {},
    isForced: Boolean(response.is_forced),
    details: response.details ?? {},
    timestamp: asString(response.timestamp),
    stale: Boolean(response.stale),
  }
}

export function getApiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message
  }
  if (error instanceof Error && error.message) {
    return error.message
  }
  return 'Unable to reach the Sovereign backend.'
}

export const api = {
  getStocks: async (): Promise<SignalData[]> => {
    const records = await fetchJson<BackendStockRecord[]>('/api/stocks')
    return records.map(normalizeStockRecord)
  },

  getRegime: async (): Promise<MarketRegimeData> => {
    const payload = await fetchJson<BackendRegimeStatusResponse>('/api/regime_status')
    return normalizeRegimeResponse(payload)
  },

  getHealth: async (): Promise<HealthResponse> => {
    return fetchJson<HealthResponse>('/api/health')
  },

  getReport: async (symbol: string): Promise<MarkdownReportResponse> => {
    return fetchJson<MarkdownReportResponse>(`/api/reports/${symbol}`)
  },
}

export type { MarketRegimeData, SignalData }
