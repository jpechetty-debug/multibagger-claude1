import {
  type BackendRegimeStatusResponse,
  type BackendStockRecord,
  type HealthResponse,
  type MarkdownReportResponse,
  type MarketRegimeData,
  type SignalAction,
  type SignalData,
  type HistoryPoint,
  type ThesisResponse,
  type ValuationData,
  type QuarterlyTimeline,
  type DataFreshnessResponse,
  type ProviderHealthResponse,
  type UniverseQualityResponse,
  type ScoreDistributionResponse,
  type ScoreExplanationResponse,
  type CalibrationReportResponse,
} from './contracts'

const BASE_URL = ''
const API_KEY_HEADER = 'X-API-Key'

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
  const apiKey = import.meta.env.VITE_SOVEREIGN_API_KEY?.trim()
  const requestInit = apiKey
    ? { headers: { [API_KEY_HEADER]: apiKey } }
    : undefined
  const response = requestInit
    ? await fetch(`${BASE_URL}${path}`, requestInit)
    : await fetch(`${BASE_URL}${path}`)
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

function normalizeAction(rating: unknown, score: number, record?: BackendStockRecord): SignalAction {
  const normalizedRating = asString(rating).toUpperCase()
  if (
    normalizedRating === 'BUY' ||
    normalizedRating === 'WATCH' ||
    normalizedRating === 'REJECT' ||
    normalizedRating === 'DISQUALIFIED'
  ) {
    // Block BUY label if data is stale (> 5 days old)
    if (normalizedRating === 'BUY' && record) {
      const asOfDate = record.as_of_date ?? record.As_Of_Date
      if (asOfDate) {
        const ageDays = Math.floor(
          (Date.now() - new Date(String(asOfDate)).getTime()) / 86400000
        )
        if (ageDays > 5) return 'WATCH'
      }
    }
    return normalizedRating
  }

  // Institutional Grade Thresholds (v3.5 Hardening)
  if (score >= 92) return 'BUY'           // Radical High Conviction
  if (score >= 80) return 'WATCH'         // Potential Candidates
  if (score >= 60) return 'REJECT'        // Neutral/Weak
  return 'DISQUALIFIED'                   // Junk/Incomplete
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
    action: normalizeAction(record.rating ?? record.Rating, score, record),
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

  getThesis: async (symbol: string): Promise<ThesisResponse> => {
    return fetchJson<ThesisResponse>(`/api/thesis/${symbol}`)
  },

  getHistory: async (symbol: string): Promise<HistoryPoint[]> => {
    return fetchJson<HistoryPoint[]>(`/api/history/${symbol}`)
  },

  getValuation: async (symbol: string): Promise<ValuationData> => {
    return fetchJson<ValuationData>(`/api/valuation/${symbol}`)
  },

  getQuarterlyTimeline: async (symbol: string): Promise<QuarterlyTimeline> => {
    return fetchJson<QuarterlyTimeline>(`/api/quarterly-results/${symbol}`)
  },

  getDataFreshness: async (): Promise<DataFreshnessResponse> => {
    return fetchJson<DataFreshnessResponse>('/api/data-freshness')
  },

  getProviderHealth: async (): Promise<ProviderHealthResponse> => {
    return fetchJson<ProviderHealthResponse>('/api/provider-health')
  },

  getUniverseQuality: async (): Promise<UniverseQualityResponse> => {
    return fetchJson<UniverseQualityResponse>('/api/universe-quality')
  },

  getScoreDistribution: async (): Promise<ScoreDistributionResponse> => {
    return fetchJson<ScoreDistributionResponse>('/api/score-distribution')
  },

  getScoreExplanation: async (symbol: string): Promise<ScoreExplanationResponse> => {
    return fetchJson<ScoreExplanationResponse>(`/api/score-explain/${symbol}`)
  },

  getCalibrationReport: async (): Promise<CalibrationReportResponse> => {
    return fetchJson<CalibrationReportResponse>('/api/calibration-report')
  },
}

export type { MarketRegimeData, SignalData }
