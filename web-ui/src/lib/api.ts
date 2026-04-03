// Sovereign API Client v9.5
const BASE_URL = ''

export interface MarketRegimeData {
  regime: 'BULL' | 'BEAR' | 'SIDEWAYS' | 'VOLATILE'
  reason: string
  india_vix: number
  momentum_accel: number
  breadth_ratio: number
  advance_count: number
  decline_count: number
}

export interface SignalData {
  symbol: string
  name: string
  price: number
  change_pct: number
  score: number
  action: 'BUY' | 'WATCH' | 'REJECT' | 'DISQUALIFIED'
  sector: string
  Quality_Score?: number
  Growth_Score?: number
  Valuation_Score?: number
  Momentum_Score?: number
}

export const api = {
  getStocks: async (): Promise<SignalData[]> => {
    const res = await fetch(`${BASE_URL}/api/stocks`)
    if (!res.ok) throw new Error('Failed to fetch stocks')
    return res.json()
  },
  
  getRegime: async (): Promise<MarketRegimeData> => {
    const res = await fetch(`${BASE_URL}/api/regime_status`)
    if (!res.ok) throw new Error('Failed to fetch regime')
    return res.json()
  },
  
  getVix: async (): Promise<number> => {
    const res = await fetch(`${BASE_URL}/api/vix`)
    if (!res.ok) return 14 // Default fallback
    const data = await res.json()
    return data.vix
  },
  
  getReport: async (symbol: string) => {
    const res = await fetch(`${BASE_URL}/api/reports/${symbol}`)
    if (!res.ok) return null
    return res.json()
  }
}
