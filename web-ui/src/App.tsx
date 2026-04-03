import { useState, useEffect, useCallback } from 'react'
import { Header } from './components/layout/Header'
import { SignalGrid } from './components/signals/SignalGrid'
import { FloorDock } from './components/layout/FloorDock'
import { api, SignalData, MarketRegimeData } from './lib/api'

export default function App() {
  const [activeTab, setActiveTab] = useState('Signals')
  const [signals, setSignals] = useState<SignalData[]>([])
  const [regime, setRegime] = useState<MarketRegimeData | null>(null)
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')

  const loadData = useCallback(async () => {
    try {
      const [stockData, regimeData] = await Promise.all([
        api.getStocks(),
        api.getRegime()
      ])
      setSignals(stockData)
      setRegime(regimeData)
    } catch (err) {
      console.error('Failed to load Sovereign data:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 30000) // 30s refresh
    return () => clearInterval(interval)
  }, [loadData])

  const filteredSignals = signals.filter(s => 
    s.symbol.toLowerCase().includes(searchTerm.toLowerCase()) ||
    s.name.toLowerCase().includes(searchTerm.toLowerCase())
  )

  return (
    <div className="min-h-screen bg-brand-bg text-brand-text font-sans selection:bg-brand-accent/30 selection:text-brand-accent grainy">
      <Header 
        regime={regime?.regime} 
        acceleration={0.32} // Acceleration is 0.32 in v9.1
      />

      <SignalGrid 
        signals={filteredSignals.slice(0, 11)} // Limit for the fragmented grid feel
        onSearch={setSearchTerm} 
      />

      <FloorDock 
        activeTab={activeTab} 
        onTabChange={setActiveTab} 
      />

      {/* 🔮 ASYMMETRIC DECORATIONS */}
      <div className="fixed top-[40%] -left-8 w-32 h-32 bg-brand-accent/5 rounded-full blur-[100px] pointer-events-none" />
      <div className="fixed bottom-0 right-0 w-64 h-64 bg-brand-rose/5 rounded-full blur-[150px] pointer-events-none" />
    </div>
  )
}
