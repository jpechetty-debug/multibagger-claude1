import React, { useEffect, useState, useMemo } from 'react'
import { api } from '../../lib/api'
import type { SwingTrade } from '../../lib/contracts'
import { SwingTradeCard } from './SwingTradeCard'
import { Activity, AlertTriangle, RefreshCw, Search, Filter } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

export function SwingTradeGrid() {
  const [trades, setTrades] = useState<SwingTrade[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  
  // Filtering & Sorting State
  const [search, setSearch] = useState('')
  const [riskFilter, setRiskFilter] = useState<'ALL' | 'LOW' | 'MEDIUM' | 'HIGH'>('ALL')
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'ACTIVE' | 'PENDING' | 'EXTENDED' | 'STALE'>('ALL')
  const [sortBy, setSortBy] = useState<'RANK' | 'SCORE' | 'RR' | 'TARGET'>('RANK')

  const fetchTrades = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getSwingTrades()
      setTrades(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch swing trades')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void fetchTrades()
  }, [])

  const filteredTrades = useMemo(() => {
    let result = [...trades]

    // 1. Filter
    if (search) {
      const q = search.toLowerCase()
      result = result.filter(t => t.symbol.toLowerCase().includes(q))
    }
    if (riskFilter !== 'ALL') {
      result = result.filter(t => t.risk === riskFilter)
    }
    if (statusFilter !== 'ALL') {
      result = result.filter(t => t.status === statusFilter)
    }

    // 2. Sort
    result.sort((a, b) => {
      if (sortBy === 'SCORE') return b.score - a.score
      if (sortBy === 'RR') return b.reward_risk_ratio - a.reward_risk_ratio
      if (sortBy === 'TARGET') return b.target_pct - a.target_pct
      return 0 // Default rank (already sorted by backend)
    })

    return result
  }, [trades, search, riskFilter, statusFilter, sortBy])

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh] text-brand-text-dim gap-4">
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ repeat: Infinity, duration: 1.5, ease: "linear" }}
        >
          <RefreshCw className="w-8 h-8 text-brand-accent opacity-50" />
        </motion.div>
        <div className="text-[10px] uppercase tracking-[0.2em] font-bold animate-pulse">Scanning for Swing Opportunities...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh] p-8 max-w-lg mx-auto text-center">
        <AlertTriangle className="w-12 h-12 text-brand-rose mb-4 opacity-80" />
        <h3 className="text-xl font-bold text-white mb-2 tracking-tight uppercase italic">System Corruption Detected</h3>
        <p className="text-sm text-brand-text-dim mb-6 font-mono">{error}</p>
        <button 
          onClick={fetchTrades}
          className="px-8 py-3 bg-brand-rose/10 text-brand-rose border border-brand-rose/30 text-[10px] font-black uppercase tracking-[0.2em] hover:bg-brand-rose/20 transition-all active:scale-95"
        >
          Initiate Reboot Sequence
        </button>
      </div>
    )
  }

  return (
    <div className="w-full max-w-7xl mx-auto px-4 py-8 pb-32">
      {/* Header Section */}
      <div className="mb-12 flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-white/5 pb-8">
        <div>
          <h1 className="text-4xl font-black text-white tracking-tighter flex items-center gap-4 italic uppercase">
            <Activity className="w-10 h-10 text-brand-accent" />
            Tactical Swings
          </h1>
          <p className="text-[10px] text-brand-text-dim uppercase tracking-[0.3em] font-bold mt-3 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-brand-accent animate-ping" />
            {filteredTrades.length} Active Intelligence Reports Detected
          </p>
        </div>

        {/* Toolbar */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative group">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-brand-text-dim group-focus-within:text-brand-accent transition-colors" />
            <input 
              type="text"
              placeholder="SEARCH SYMBOL..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="bg-brand-bg/50 border border-white/10 pl-9 pr-4 py-2 text-[10px] font-bold tracking-widest text-white focus:outline-none focus:border-brand-accent/50 w-48 transition-all"
            />
          </div>

          <select 
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as any)}
            className="bg-brand-bg/50 border border-white/10 px-3 py-2 text-[10px] font-bold tracking-widest text-brand-text-dim focus:outline-none focus:border-brand-accent/50 transition-all uppercase"
          >
            <option value="RANK">SORT: SYSTEM RANK</option>
            <option value="SCORE">SORT: QUANT SCORE</option>
            <option value="RR">SORT: RISK/REWARD</option>
            <option value="TARGET">SORT: TARGET %</option>
          </select>

          <button
            onClick={fetchTrades}
            className="flex items-center gap-2 bg-brand-accent/10 border border-brand-accent/30 px-4 py-2 text-[10px] font-black uppercase tracking-widest text-brand-accent hover:bg-brand-accent/20 transition-all active:scale-95"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            REFRESH
          </button>
        </div>
      </div>

      {/* Filters Strip */}
      <div className="mb-8 flex items-center gap-6 overflow-x-auto pb-2 no-scrollbar">
        <div className="flex items-center gap-2 text-[9px] font-black text-brand-text-dim uppercase tracking-widest">
          <Filter className="w-3 h-3" /> Risk Profile:
        </div>
        <div className="flex gap-1">
          {['ALL', 'LOW', 'MEDIUM', 'HIGH'].map(f => (
            <button
              key={f}
              onClick={() => setRiskFilter(f as any)}
              className={`px-3 py-1 text-[9px] font-black tracking-tighter uppercase transition-all ${
                riskFilter === f 
                  ? 'bg-brand-accent text-brand-bg' 
                  : 'text-brand-text-dim hover:text-white border border-white/5 hover:border-white/20'
              }`}
            >
              {f}
            </button>
          ))}
        </div>

        <div className="w-[1px] h-4 bg-white/10 mx-2" />

        <div className="flex items-center gap-2 text-[9px] font-black text-brand-text-dim uppercase tracking-widest">
          <Activity className="w-3 h-3" /> Status:
        </div>
        <div className="flex gap-1">
          {['ALL', 'ACTIVE', 'PENDING', 'EXTENDED', 'STALE'].map(f => (
            <button
              key={f}
              onClick={() => setStatusFilter(f as any)}
              className={`px-3 py-1 text-[9px] font-black tracking-tighter uppercase transition-all ${
                statusFilter === f 
                  ? 'bg-white text-brand-bg' 
                  : 'text-brand-text-dim hover:text-white border border-white/5 hover:border-white/20'
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* Grid */}
      {filteredTrades.length === 0 ? (
        <div className="flex flex-col items-center justify-center min-h-[40vh] border border-dashed border-white/10 rounded-3xl">
          <Search className="w-12 h-12 text-white/5 mb-4" />
          <p className="text-xs font-mono tracking-widest uppercase text-brand-text-dim">No matching tactical setups found</p>
          <button 
            onClick={() => { setSearch(''); setRiskFilter('ALL'); setStatusFilter('ALL'); }}
            className="mt-4 text-[10px] font-black text-brand-accent uppercase tracking-widest hover:underline"
          >
            Clear All Filters
          </button>
        </div>
      ) : (
        <motion.div 
          layout
          className="grid grid-cols-1 xl:grid-cols-2 gap-8"
        >
          <AnimatePresence mode='popLayout'>
            {filteredTrades.map((trade) => (
              <motion.div
                key={trade.symbol}
                layout
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ duration: 0.4, ease: [0.23, 1, 0.32, 1] }}
              >
                <SwingTradeCard trade={trade} />
              </motion.div>
            ))}
          </AnimatePresence>
        </motion.div>
      )}
    </div>
  )
}
