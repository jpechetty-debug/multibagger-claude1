import {
  Suspense,
  lazy,
  startTransition,
  useCallback,
  useDeferredValue,
  useEffect,
  useState,
} from 'react'
import { Header } from './components/layout/Header'
import { Routes, Route } from 'react-router-dom'
import { SignalGrid } from './components/signals/SignalGrid'
import { SwingTradeGrid } from './components/signals/SwingTradeGrid'
import { StrategyIntelligence } from './components/signals/StrategyIntelligence'
import { FloorDock } from './components/layout/FloorDock'
import { api, getApiErrorMessage } from './lib/api'
import type { MarketRegimeData, SignalData } from './lib/contracts'

const StockDetail = lazy(() =>
  import('./pages/StockDetail').then((module) => ({ default: module.StockDetail })),
)

const WatchlistPage = lazy(() =>
  import('./pages/Watchlist').then((module) => ({ default: module.Watchlist })),
)

const ScoreReportPage = lazy(() =>
  import('./pages/ScoreReport').then((module) => ({ default: module.ScoreReport })),
)

function RouteFallback() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center p-8 font-mono text-xs font-bold uppercase tracking-widest text-brand-primary">
      Loading terminal node...
    </div>
  )
}

export default function App() {
  const [activeTab, setActiveTab] = useState('Signals')
  const [signals, setSignals] = useState<SignalData[]>([])
  const [regime, setRegime] = useState<MarketRegimeData | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [lastUpdated, setLastUpdated] = useState<string | null>(null)
  const [highReliabilityOnly, setHighReliabilityOnly] = useState(false)

  const deferredSearchTerm = useDeferredValue(searchTerm)
  const normalizedSearchTerm = deferredSearchTerm.trim().toLowerCase()

  const loadData = useCallback(async (mode: 'initial' | 'refresh' = 'refresh') => {
    if (mode === 'initial') {
      setLoading(true)
    } else {
      setRefreshing(true)
    }

    try {
      const [stockData, regimeData] = await Promise.all([
        api.getStocks(),
        api.getRegime(),
      ])

      startTransition(() => {
        setSignals(stockData)
        setRegime(regimeData)
        setErrorMessage(null)
        setLastUpdated(new Date().toISOString())
      })
    } catch (error) {
      setErrorMessage(getApiErrorMessage(error))
    } finally {
      if (mode === 'initial') {
        setLoading(false)
      } else {
        setRefreshing(false)
      }
    }
  }, [])

  useEffect(() => {
    void loadData('initial')
    const interval = setInterval(() => {
      void loadData('refresh')
    }, 30000)

    return () => clearInterval(interval)
  }, [loadData])

  const filteredSignals = signals.filter((signal) => {
    const matchesSearch = normalizedSearchTerm
      ? signal.symbol.toLowerCase().includes(normalizedSearchTerm) ||
        signal.name.toLowerCase().includes(normalizedSearchTerm) ||
        signal.sector.toLowerCase().includes(normalizedSearchTerm)
      : true
    
    const matchesReliability = highReliabilityOnly ? signal.dataQuality >= 90 : true
    
    return matchesSearch && matchesReliability
  })

  return (
    <div className="min-h-screen bg-brand-bg text-brand-text font-sans selection:bg-brand-primary/30 selection:text-brand-primary grainy">
      {regime?.regime === 'BLACK' && (
        <div className="hazard-pattern border-b-2 border-brand-rose p-2 text-center text-[10px] font-black uppercase tracking-[0.2em] text-brand-rose animate-pulse">
          CRITICAL VOLATILITY: Market halted by Risk Governor (VIX {regime.vix})
        </div>
      )}

      <Header
        regime={regime?.regime}
        acceleration={regime?.momentumAccel ?? 0}
        isForced={regime?.isForced ?? false}
        isStale={regime?.stale ?? false}
        lastUpdated={regime?.timestamp || lastUpdated}
      />

      <Routes>
        <Route path="/" element={
          <>
            {activeTab === 'Signals' && (
              <SignalGrid
                signals={filteredSignals}
                totalSignalCount={signals.length}
                searchTerm={searchTerm}
                loading={loading}
                isRefreshing={refreshing}
                error={errorMessage}
                lastUpdated={lastUpdated}
                onRetry={() => void loadData('initial')}
                onSearch={setSearchTerm}
                highReliabilityOnly={highReliabilityOnly}
                onToggleReliability={setHighReliabilityOnly}
              />
            )}
            {activeTab === 'Swing Trades' && (
              <>
                <StrategyIntelligence />
                <SwingTradeGrid />
              </>
            )}
            <FloorDock
              activeTab={activeTab}
              onTabChange={setActiveTab}
            />
          </>
        } />
        <Route
          path="/stock/:symbol"
          element={
            <Suspense fallback={<RouteFallback />}>
              <StockDetail />
            </Suspense>
          }
        />
        <Route
          path="/watchlist"
          element={
            <Suspense fallback={<RouteFallback />}>
              <WatchlistPage />
            </Suspense>
          }
        />
        <Route
          path="/score-report"
          element={
            <Suspense fallback={<RouteFallback />}>
              <ScoreReportPage />
            </Suspense>
          }
        />
      </Routes>

      <div className="fixed top-[20%] -left-16 w-64 h-64 bg-brand-primary/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="fixed bottom-0 -right-16 w-96 h-96 bg-brand-secondary/10 rounded-full blur-[150px] pointer-events-none" />
    </div>
  )
}
