import {
  startTransition,
  useCallback,
  useDeferredValue,
  useEffect,
  useState,
} from 'react'
import { Header } from './components/layout/Header'
import { Routes, Route } from 'react-router-dom'
import { SignalGrid } from './components/signals/SignalGrid'
import { FloorDock } from './components/layout/FloorDock'
import { StockDetail } from './pages/StockDetail'
import { api, getApiErrorMessage } from './lib/api'
import type { MarketRegimeData, SignalData } from './lib/contracts'

export default function App() {
  const [activeTab, setActiveTab] = useState('Signals')
  const [signals, setSignals] = useState<SignalData[]>([])
  const [regime, setRegime] = useState<MarketRegimeData | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [lastUpdated, setLastUpdated] = useState<string | null>(null)

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

  const filteredSignals = normalizedSearchTerm
    ? signals.filter((signal) => {
        const symbol = signal.symbol.toLowerCase()
        const name = signal.name.toLowerCase()
        const sector = signal.sector.toLowerCase()
        return (
          symbol.includes(normalizedSearchTerm) ||
          name.includes(normalizedSearchTerm) ||
          sector.includes(normalizedSearchTerm)
        )
      })
    : signals

  return (
    <div className="min-h-screen bg-brand-bg text-brand-text font-sans selection:bg-brand-accent/30 selection:text-brand-accent grainy">
      {regime?.regime === 'BLACK' && (
        <div className="hazard-pattern border-b-2 border-brand-rose p-2 text-center text-[10px] font-black uppercase tracking-[0.2em] text-brand-rose animate-pulse">
          ⚠️ CRITICAL VOLATILITY: Market Halted by Risk Governor (VIX {regime.vix}) ⚠️
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
            />
            <FloorDock
              activeTab={activeTab}
              onTabChange={setActiveTab}
            />
          </>
        } />
        <Route path="/stock/:symbol" element={<StockDetail />} />
      </Routes>

      <div className="fixed top-[40%] -left-8 w-32 h-32 bg-brand-accent/5 rounded-full blur-[100px] pointer-events-none" />
      <div className="fixed bottom-0 right-0 w-64 h-64 bg-brand-rose/5 rounded-full blur-[150px] pointer-events-none" />
    </div>
  )
}
