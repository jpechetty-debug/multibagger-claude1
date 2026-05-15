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

export interface DataFreshnessResponse {
  status: 'FRESH' | 'STALE' | 'EXPIRED' | 'UNKNOWN'
  latest_as_of_date: string | null
  age_days: number
  source: string
  data_quality: number
  scheduled_refresh: {
    status: string
    last_scan?: string | null
    age_hours?: number
    next_expected?: string
  }
  universe_counts: {
    fresh: number
    stale: number
    expired: number
    incomplete: number
    total: number
  }
}

export interface ProviderHealthItem {
  name: string
  success_rate: number
  total_calls: number
  last_success: string | null
  last_failure: string | null
  status: 'healthy' | 'degraded' | 'down' | 'unknown'
}

export interface ProviderHealthResponse {
  providers: ProviderHealthItem[]
}

export interface UniverseQualityResponse {
  total_stocks: number
  fresh_count: number
  stale_count: number
  expired_count: number
  incomplete_count: number
  stale_pct: number
  alert_active: boolean
  alert_message: string | null
}

export interface ScoreDistributionResponse {
  deciles: Record<string, number>
  stats: {
    mean: number
    median: number
    std: number
    min: number
    max: number
    p5: number
    p25: number
    p75: number
    p95: number
  }
  graveyard_count: number
  graveyard_pct: number
  top5_threshold: number
  total: number
  sector_breakdown: Record<string, {
    count: number
    mean: number
    median: number
    min: number
    max: number
    std: number
  }>
}

export interface ScoreExplanationResponse {
  symbol: string
  score: number
  sector: string
  top_positive_drivers: Array<{ factor: string; value: string; impact: string }>
  top_penalties: Array<{ factor: string; value: string; impact: string }>
  active_ceilings: Array<{ name: string; cap: number; active: boolean }>
  checklist_status: {
    items: Record<string, boolean>
    passed: number
    total: number
    grade: string
  }
  missing_factors: string[]
  data_quality: number
  score_delta: {
    previous_score: number
    delta: number
    previous_date: string
    direction: 'UP' | 'DOWN' | 'FLAT'
    reason: string
  } | null
}

export interface CalibrationReportResponse {
  distribution: ScoreDistributionResponse
  sector_distribution: { sectors: Record<string, unknown> }
  calibration_issues: Array<{ severity: string; issue: string; fix: string }>
  top5_rarity_pct: number
  effective_range: string
  health: 'GOOD' | 'NEEDS_ATTENTION' | 'POOR'
  timestamp: string
}

export interface SwingTrade {
  symbol: string
  status: string
  type: string
  risk: string
  date: string
  source_as_of_date?: string | null
  snapshot_age_days?: number | null
  entry_range: [number, number]
  target: number
  target_pct: number
  sl: number
  potential_left_pct: number
  ltp: number
  ltp_change_pct: number
  ret_1m_pct: number
  analysis: string
  score: number
  rating?: string
  data_quality?: number
  market_cap_cr?: number
  f_score?: number | null
  pe_ratio?: number | null
  debt_equity?: number | null
  quality_flags?: string[]
  reward_risk_ratio: number
}

export interface PortfolioState {
  available_capital: number
  total_deployed: number
  risk_per_trade_pct: number
  active_trades_count: number
  max_positions: number
}
export interface SwarmStatusResponse {
  status: 'online' | 'offline' | 'error'
  active_agents?: number
  current_workflow?: string | null
  health?: number
  uptime?: string
  error?: string | null
}

export interface SwarmAlert {
  id: string
  type: string
  sector: string
  label: 'G' | 'B'
  confidence: number
  message: string
  timestamp?: string
}
