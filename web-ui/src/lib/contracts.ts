export type SignalAction = 'BUY' | 'WATCH' | 'REJECT' | 'DISQUALIFIED'

export interface BackendRegimeStatusResponse {
  regime: string
  vix: number
  vix_threshold: number
  momentum_accel: number
  votes: Record<string, unknown>
  is_forced: boolean
  details: Record<string, unknown>
  timestamp: string
  stale?: boolean
  error?: string | null
}

export interface BackendStockRecord {
  Symbol?: string
  symbol?: string
  name?: string | null
  company_name?: string | null
  Price?: number | null
  price?: number | null
  Score?: number | null
  score?: number | null
  Sector?: string | null
  sector?: string | null
  Rating?: string | null
  rating?: string | null
  Ret_1M?: number | null
  ret_1m?: number | null
  Conviction_Score?: number | null
  conviction_score?: number | null
  As_Of_Date?: string | null
  as_of_date?: string | null
  [key: string]: unknown
}

export interface HealthResponse {
  status: string
  timestamp: string
  latency_reference: string
}

export interface MarkdownReportResponse {
  content: string
}

export interface MarketRegimeData {
  regime: string
  vix: number
  vixThreshold: number
  momentumAccel: number
  votes: Record<string, unknown>
  isForced: boolean
  details: Record<string, unknown>
  timestamp: string
  stale: boolean
}

export interface SignalData {
  symbol: string
  name: string
  price: number
  changePct: number
  score: number
  action: SignalAction
  sector: string
  convictionScore: number
  asOfDate: string | null
  raw: BackendStockRecord
}
