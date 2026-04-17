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

export interface HistoryPoint {
  date: string
  score: number
  price: number
}

export interface ThesisResponse {
  thesis: string
}

export interface ValuationData {
  margin_of_safety: number
  intrinsic_value: number | null
  components: {
    dcf: number | null
    graham: number | null
    epv: number | null
  }
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

export interface QuarterlyData {
  quarter: string
  date: string
  revenue: number
  profit: number
  ebitda: number
  margin: number
  ebitda_margin: number
  eps: number | null
  book_value: number | null
  revenue_growth_qoq: number | null
  profit_growth_qoq: number | null
  revenue_growth_yoy: number | null
  profit_growth_yoy: number | null
}

export interface QuarterlyTrend {
  revenue_trend: 'GROWING' | 'DECLINING' | 'FLAT' | 'INSUFFICIENT_DATA'
  profit_trend: 'GROWING' | 'DECLINING' | 'FLAT' | 'INSUFFICIENT_DATA'
  margin_trend: 'EXPANDING' | 'CONTRACTING' | 'STABLE' | 'INSUFFICIENT_DATA'
  consistency: 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN'
  avg_revenue_growth: number
  avg_profit_growth: number
  avg_margin: number
  quarters_with_growth: number
  total_quarters: number
}

export interface QuarterlyAlert {
  type: 'WARNING' | 'POSITIVE' | 'ERROR'
  message: string
  severity: 'HIGH' | 'MEDIUM' | 'LOW'
}

export interface QuarterlyTimeline {
  symbol: string
  company_name: string
  quarters: QuarterlyData[]
  trends: QuarterlyTrend
  alerts: QuarterlyAlert[]
  timestamp: string
}
