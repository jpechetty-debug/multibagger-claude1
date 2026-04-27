import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, BrainCircuit, Activity, BarChart4, Heart, Printer } from 'lucide-react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Legend
} from 'recharts'
import { api } from '../lib/api'
import type { SignalData, HistoryPoint } from '../lib/contracts'
import { MetricExplainer } from '../components/metrics/MetricExplainer'
import QuarterlyTimeline from '../components/signals/QuarterlyTimeline'
import { ScoreExplainer } from '../components/signals/ScoreExplainer'
import { RedFlagPanel } from '../components/signals/RedFlagPanel'
import { useWatchlist } from '../lib/useWatchlist'

function formatVal(val: unknown, fallback: string = '-'): string {
  if (val === null || val === undefined) return fallback
  return String(val)
}

function formatNum(val: unknown, digits: number = 2): string {
  if (typeof val === 'number') return val.toFixed(digits)
  if (typeof val === 'string' && !isNaN(Number(val))) return Number(val).toFixed(digits)
  return '-'
}

export function StockDetail() {
  const { symbol } = useParams<{ symbol: string }>()
  const { isInWatchlist, toggleWatchlist } = useWatchlist()
  
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  
  const [stock, setStock] = useState<SignalData | null>(null)
  const [history, setHistory] = useState<HistoryPoint[]>([])
  const [thesis, setThesis] = useState<string>('No thesis generated.')

  useEffect(() => {
    async function loadDetail() {
      if (!symbol) return
      setLoading(true)
      try {
        const [stocks, hist, thes] = await Promise.all([
          api.getStocks(),
          api.getHistory(symbol),
          api.getThesis(symbol)
        ])
        
        const matched = stocks.find(s => s.symbol === symbol)
        if (matched) setStock(matched)
        
        setHistory(hist || [])
        setThesis(thes?.thesis || 'No thesis generated. Ensure LLM is running.')
        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error fetching details.')
      } finally {
        setLoading(false)
      }
    }
    
    void loadDetail()
  }, [symbol])

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-brand-bg text-brand-text">
        <div className="animate-pulse font-mono tracking-widest text-brand-accent uppercase font-bold">
          [ DECRYPTING TERMINAL FEED ]
        </div>
      </div>
    )
  }

  if (error || !stock) {
    return (
      <div className="p-8 font-mono text-brand-rose">
        <h2 className="text-2xl font-black mb-4">SYSTEM ERROR</h2>
        <p>{error || 'Stock not found in current signal universe.'}</p>
        <Link to="/" className="mt-8 inline-block border-2 border-brand-rose px-4 py-2 hover:bg-brand-rose/20 text-brand-rose">
          &lt; RETURN TO MAIN TERMINAL
        </Link>
      </div>
    )
  }

  const raw = stock.raw
  const isHighConviction = stock.score > 85
  const watched = isInWatchlist(stock.symbol)
  return (
    <div className="min-h-screen bg-brand-bg text-brand-text p-4 md:p-8 pb-32">
      {/* Navigation */}
      <div className="flex items-center gap-4 mb-8">
        <Link 
          to="/" 
          className="inline-flex items-center gap-2 font-mono text-sm tracking-widest text-brand-text-dim hover:text-brand-accent transition-colors uppercase border border-transparent hover:border-brand-accent/20 px-3 py-1.5 rounded"
        >
          <ArrowLeft size={16} /> 
          Back to Dashboard
        </Link>
        <div className="flex-1" />
        <button
          type="button"
          onClick={() => toggleWatchlist(stock.symbol)}
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-mono font-bold uppercase tracking-widest transition-all ${
            watched
              ? 'border-brand-rose/30 bg-brand-rose/10 text-brand-rose hover:bg-brand-rose/20'
              : 'border-brand-border text-brand-text-dim hover:border-brand-accent/40 hover:text-brand-accent'
          }`}
        >
          <Heart size={14} className={watched ? 'fill-brand-rose' : ''} />
          {watched ? 'Watchlisted' : 'Watch'}
        </button>
        <button
          type="button"
          onClick={() => window.print()}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-brand-border text-xs font-mono font-bold uppercase tracking-widest text-brand-text-dim hover:border-brand-accent/40 hover:text-brand-accent transition-colors"
        >
          <Printer size={14} />
          Export
        </button>
      </div>

      {/* Header Section */}
      <div className="brutalist-card p-6 md:p-8 mb-8 border-brand-accent/30 group">
         <div className="flex flex-col md:flex-row md:items-start justify-between gap-6">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <h1 className="font-display text-4xl md:text-5xl font-black tracking-tight group-hover:text-brand-accent transition-colors">
                  {stock.symbol}
                </h1>
                <div className={`px-2 py-1 text-xs font-mono font-bold tracking-tighter rounded border ${
                    stock.action === 'BUY' ? 'border-brand-accent bg-brand-accent/10 text-brand-accent' :
                    stock.action === 'WATCH' ? 'border-brand-gold bg-brand-gold/10 text-brand-gold' :
                    'border-white/20 bg-white/5 text-brand-text-dim'
                }`}>
                  {stock.action}
                </div>
              </div>
              <p className="font-mono text-lg text-brand-text-dim uppercase tracking-widest mb-1">{stock.name}</p>
              <p className="font-mono text-sm text-brand-text-dim uppercase">{stock.sector}</p>
            </div>
            
            <div className="flex flex-col items-end text-right">
              <div className="font-display text-4xl font-medium tracking-tight">
                Rs {stock.price.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </div>
              <div className={`font-mono font-bold text-sm ${stock.changePct >= 0 ? 'text-brand-accent' : 'text-brand-rose'}`}>
                {stock.changePct >= 0 ? '+' : ''}{stock.changePct.toFixed(2)}%
              </div>
            </div>
         </div>
         
         {/* Top-line scores */}
         <div className="mt-8 grid grid-cols-2 md:grid-cols-4 gap-4 pt-6 border-t border-brand-border">
            <div className="p-4 bg-black/40 border border-white/5 flex flex-col">
              <MetricExplainer metric="Conviction">
                <span className="font-mono text-xs uppercase text-brand-text-dim">Score</span>
              </MetricExplainer>
              <div className={`mt-2 font-display text-3xl font-black ${isHighConviction ? 'text-brand-accent' : 'text-brand-gold'}`}>
                {Math.round(stock.score)}<span className="text-lg opacity-50">/100</span>
              </div>
            </div>
            
            <div className="p-4 bg-black/40 border border-white/5 flex flex-col">
              <MetricExplainer metric="F-Score">
                <span className="font-mono text-xs uppercase text-brand-text-dim">Piotroski</span>
              </MetricExplainer>
              <div className="mt-2 font-display text-3xl font-black text-brand-text">
                {formatVal(raw.f_score ?? raw.F_Score)}<span className="text-lg opacity-50">/9</span>
              </div>
            </div>

            <div className="p-4 bg-black/40 border border-white/5 flex flex-col">
              <MetricExplainer metric="P/E Ratio">
                <span className="font-mono text-xs uppercase text-brand-text-dim">Valuation</span>
              </MetricExplainer>
              <div className="mt-2 font-display text-3xl font-black text-brand-text">
                {formatNum(raw.pe_ratio ?? raw.PE_Ratio, 1)}
              </div>
            </div>

            <div className="p-4 bg-black/40 border border-white/5 flex flex-col">
              <MetricExplainer metric="5Y CAGR">
                <span className="font-mono text-xs uppercase text-brand-text-dim">Growth</span>
              </MetricExplainer>
              <div className="mt-2 font-display text-3xl font-black text-brand-accent">
                {formatVal(raw.sales_cagr_5y ?? raw['Sales_Growth_5Y%'])}%
              </div>
            </div>
         </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-8">
        {/* Left Column: Chart & Deep Metrics */}
        <div className="xl:col-span-2 space-y-8">
          
          {/* Chart Card */}
          <div className="brutalist-card p-6">
            <div className="flex items-center gap-2 mb-6">
              <Activity className="text-brand-accent" size={20} />
              <h2 className="font-mono text-lg font-bold uppercase tracking-widest text-brand-text">Historical Performance & Signals</h2>
            </div>
            <div className="h-80 w-full">
              {history.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={history} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" vertical={false} />
                    <XAxis 
                      dataKey="date" 
                      stroke="#6d7fa8" 
                      tick={{ fill: '#6d7fa8', fontSize: 12, fontFamily: 'Geist Mono, monospace' }} 
                      tickFormatter={(val) => {
                        try { return new Date(formatVal(val)).toLocaleDateString(undefined, { month: 'short', year: '2-digit'}) }
                        catch { return formatVal(val) }
                      }}
                    />
                    <YAxis 
                      yAxisId="left" 
                      stroke="#c9d4f0" 
                      tick={{ fill: '#c9d4f0', fontSize: 12, fontFamily: 'Geist Mono, monospace' }} 
                      domain={['auto', 'auto']}
                    />
                    <YAxis 
                      yAxisId="right" 
                      orientation="right" 
                      stroke="#00ffa3" 
                      tick={{ fill: '#00ffa3', fontSize: 12, fontFamily: 'Geist Mono, monospace' }} 
                      domain={[0, 100]}
                    />
                    <RechartsTooltip 
                      contentStyle={{ backgroundColor: '#080c17', border: '2px solid rgba(255, 255, 255, 0.1)', fontFamily: 'Geist Mono, monospace', fontSize: '12px' }}
                      itemStyle={{ color: '#c9d4f0' }}
                    />
                    <Legend wrapperStyle={{ fontFamily: 'Geist Mono, monospace', fontSize: '12px', paddingTop: '20px' }} />
                    <Line yAxisId="left" type="monotone" dataKey="price" name="Price (Rs)" stroke="#c9d4f0" strokeWidth={2} dot={false} activeDot={{ r: 6, fill: '#c9d4f0' }} />
                    <Line yAxisId="right" type="stepAfter" dataKey="score" name="Sovereign Score" stroke="#00ffa3" strokeWidth={2} dot={false} strokeOpacity={0.8} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="w-full h-full flex items-center justify-center font-mono text-sm text-brand-text-dim border border-dashed border-white/10">
                  Insufficient historical data available.
                </div>
              )}
            </div>
          </div>

          {/* Expanded Metrics Details */}
          <div className="brutalist-card p-6">
            <div className="flex items-center gap-2 mb-6 border-b border-white/10 pb-4">
              <BarChart4 className="text-brand-gold" size={20} />
              <h2 className="font-mono text-lg font-bold uppercase tracking-widest text-brand-text">Component Breakdown</h2>
            </div>
            
            <div className="grid grid-cols-2 md:grid-cols-3 gap-y-6 gap-x-4">
              <div className="flex flex-col gap-1">
                <MetricExplainer metric="ROE" label="Avg ROE (5Y)">
                  <span className="font-display font-medium text-lg">{formatVal(raw.avg_roe_5y ?? raw['Avg_ROE_5Y%'])}%</span>
                </MetricExplainer>
              </div>
              <div className="flex flex-col gap-1">
                <MetricExplainer metric="Margin of Safety" label="Margin of Safety">
                  <span className="font-display font-medium text-lg">{formatVal(raw.value_gap ?? raw['Value_Gap%'])}%</span>
                </MetricExplainer>
              </div>
              <div className="flex flex-col gap-1">
                <MetricExplainer metric="Sigmoid" label="ML Prediction">
                  <span className="font-display font-medium text-lg">{formatVal(raw.ml_predicted_return ?? raw['ML_Predicted_Return'])}%</span>
                </MetricExplainer>
              </div>
              <div className="flex flex-col gap-1 text-xs text-brand-text-dim font-mono">
                Debt/Equity: <span className="text-brand-text">{formatVal(raw.debt_equity)}</span>
              </div>
              <div className="flex flex-col gap-1 text-xs text-brand-text-dim font-mono">
                CFO/PAT: <span className="text-brand-text">{formatVal(raw.cfo_pat_ratio)}</span>
              </div>
              <div className="flex flex-col gap-1 text-xs text-brand-text-dim font-mono">
                Promoter Holding: <span className="text-brand-text">{formatVal(raw.promoter_holding)}%</span>
              </div>
            </div>
          </div>

          {/* Compounding Lens Metrics */}
          <div className="brutalist-card p-6">
            <div className="flex items-center gap-2 mb-6 border-b border-white/10 pb-4">
              <Activity className="text-brand-gold" size={20} />
              <h2 className="font-mono text-lg font-bold uppercase tracking-widest text-brand-text">Compounding Engine</h2>
            </div>
            
            <div className="grid grid-cols-2 md:grid-cols-3 gap-y-6 gap-x-4">
              <div className="flex flex-col gap-1">
                <span className="font-mono text-xs uppercase text-brand-text-dim">CAGR Consistency</span>
                <span className={`font-display font-bold text-lg ${raw.cagr_consistency === 'HIGH' || raw.CAGR_Consistency === 'HIGH' ? 'text-brand-accent' : raw.cagr_consistency === 'LOW' || raw.CAGR_Consistency === 'LOW' ? 'text-brand-rose' : 'text-brand-gold'}`}>
                  {formatVal(raw.cagr_consistency ?? raw.CAGR_Consistency, 'UNKNOWN')}
                </span>
              </div>
              <div className="flex flex-col gap-1 text-xs text-brand-text-dim font-mono">
                Cap Category: <span className="text-brand-text">{formatVal(raw.cap_category ?? raw.Cap_Category, 'Unknown')}</span>
              </div>
              <div className="flex flex-col gap-1 text-xs text-brand-text-dim font-mono">
                Dividend Yield: <span className="text-brand-text">{formatVal(raw.dividend_yield ?? raw.Dividend_Yield, '0')}%</span>
              </div>
              <div className="flex flex-col gap-1 text-xs text-brand-text-dim font-mono">
                Revenue 3Y: <span className="text-brand-text">{formatVal(raw.revenue_cagr_3y ?? raw.Revenue_CAGR_3Y)}%</span>
              </div>
              <div className="flex flex-col gap-1 text-xs text-brand-text-dim font-mono">
                PAT 3Y: <span className="text-brand-text">{formatVal(raw.pat_cagr_3y ?? raw.PAT_CAGR_3Y)}%</span>
              </div>
              <div className="flex flex-col gap-1 text-xs text-brand-text-dim font-mono">
                EPS 3Y: <span className="text-brand-text">{formatVal(raw.eps_cagr_3y ?? raw.EPS_CAGR_3Y)}%</span>
              </div>
            </div>
          </div>

          {/* Quarterly Results Timeline */}
          <div className="brutalist-card p-6">
            <QuarterlyTimeline symbol={symbol!} />
          </div>

          {/* Why This Score? */}
          <div className="brutalist-card p-6">
            <ScoreExplainer symbol={symbol!} />
          </div>

        </div>

        {/* Right Column: AI Thesis + Red Flags */}
        <div className="xl:col-span-1 space-y-6">
          {/* Red Flags */}
          <RedFlagPanel stock={raw} />

          {/* AI Thesis */}
          <div className="brutalist-card p-6 h-full border-brand-accent shadow-[4px_4px_0_0_#00ffa3]/20 bg-brand-accent/5">
            <div className="flex items-center gap-2 mb-6 pb-4 border-b border-brand-accent/20">
              <BrainCircuit className="text-brand-accent" size={20} />
              <h2 className="font-mono text-lg font-bold uppercase tracking-widest text-brand-accent">Sovereign Intel Thesis</h2>
            </div>
            
            <div className="prose prose-invert prose-sm max-w-none font-sans leading-relaxed text-brand-text/90">
              {thesis.split('\n\n').map((paragraph, i) => (
                <p key={i} className="mb-4">{paragraph}</p>
              ))}
            </div>
            
            <div className="mt-8 pt-4 border-t border-white/5 font-mono text-[10px] uppercase text-brand-text-dim flex items-center justify-between">
              <span>Status: Generated</span>
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-brand-accent animate-pulse" />
                Network Node Active
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
