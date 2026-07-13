import type { ReactNode } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  AlertTriangle,
  Inbox,
  LoaderCircle,
  RefreshCcw,
  Search,
  Database,
  ArrowUpDown,
} from 'lucide-react'
import { useState, useMemo } from 'react'

import type { SignalData } from '../../lib/contracts'

interface ScreenerGridProps {
  signals: SignalData[]
  totalSignalCount: number
  searchTerm: string
  loading: boolean
  isRefreshing: boolean
  error: string | null
  lastUpdated: string | null
  onRetry: () => void
  onSearch: (term: string) => void
  highReliabilityOnly: boolean
  onToggleReliability: (val: boolean) => void
}

type SortField = 'score' | 'mlRankScore' | 'roe' | 'pe' | 'fScore' | 'marketCapCr' | 'symbol'
type SortDir = 'asc' | 'desc'

export function ScreenerGrid({
  signals,
  totalSignalCount,
  searchTerm,
  loading,
  isRefreshing,
  error,
  lastUpdated,
  onRetry,
  onSearch,
  highReliabilityOnly,
  onToggleReliability,
}: ScreenerGridProps) {
  const [sortField, setSortField] = useState<SortField>('score')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDir('desc')
    }
  }

  const sortedSignals = useMemo(() => {
    const arr = [...signals]
    arr.sort((a, b) => {
      let aVal: any = a.score ?? 0
      let bVal: any = b.score ?? 0

      if (sortField === 'symbol') {
        aVal = a.symbol
        bVal = b.symbol
      } else if (sortField === 'mlRankScore') {
         aVal = Number(a.raw?.ml_predicted_return ?? 0)
         bVal = Number(b.raw?.ml_predicted_return ?? 0)
      } else if (sortField === 'fScore') {
         aVal = Number(a.raw?.f_score ?? 0)
         bVal = Number(b.raw?.f_score ?? 0)
      } else if (sortField === 'marketCapCr') {
         aVal = Number(a.raw?.market_cap_cr ?? 0)
         bVal = Number(b.raw?.market_cap_cr ?? 0)
      } else if (sortField === 'roe') {
         aVal = Number(a.raw?.avg_roe_5y ?? 0)
         bVal = Number(b.raw?.avg_roe_5y ?? 0)
      } else if (sortField === 'pe') {
         aVal = Number(a.raw?.pe_ratio ?? 0)
         bVal = Number(b.raw?.pe_ratio ?? 0)
      }

      if (typeof aVal === 'string') {
        return sortDir === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal)
      }
      return sortDir === 'asc' ? aVal - bVal : bVal - aVal
    })
    return arr
  }, [signals, sortField, sortDir])

  const isEmptyUniverse = !loading && totalSignalCount === 0
  const isEmptySearch = !loading && totalSignalCount > 0 && signals.length === 0

  return (
    <main className="p-8 pt-12 max-w-[1400px] mx-auto">
      <div className="mb-6 flex items-center justify-between">
        <div className="space-y-2">
          <h2 className="font-display text-3xl font-black tracking-tight flex items-center gap-3">
            <Database className="w-8 h-8 text-brand-primary" />
            Quantitative Screener
            <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-primary/15 border border-brand-primary/30 px-3 py-1 text-xs font-mono font-black uppercase tracking-widest text-brand-primary">
              Top 100
            </span>
          </h2>
          <p className="max-w-2xl text-sm leading-relaxed text-brand-text-dim">
            Highest-conviction picks ranked by Nexus score — top 100 by institutional grade.
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="relative w-64">
             <input
              type="text"
              value={searchTerm}
              placeholder="Filter ticker..."
              onChange={(e) => onSearch(e.target.value)}
              className="w-full bg-brand-bg/50 border border-brand-border rounded-xl px-4 py-2 text-xs font-mono focus:border-brand-primary outline-none"
            />
            <Search className="w-4 h-4 text-brand-text-dim absolute right-3 top-2.5" />
          </div>
          <button
            type="button"
            onClick={onRetry}
            className="flex items-center gap-2 rounded-xl border border-brand-primary/30 bg-brand-primary/10 px-4 py-2 text-xs font-mono font-bold uppercase tracking-widest text-brand-primary hover:border-brand-primary/60 transition-colors"
          >
            {isRefreshing ? <RefreshCcw className="h-3.5 w-3.5 animate-spin" /> : <RefreshCcw className="h-3.5 w-3.5" />}
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-6 flex items-center gap-3 rounded-2xl border border-brand-rose/20 bg-brand-rose/5 px-4 py-4">
          <AlertTriangle className="h-4 w-4 text-brand-rose" />
          <p className="text-sm text-brand-text">{error}</p>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center p-20">
           <LoaderCircle className="h-8 w-8 animate-spin text-brand-primary" />
        </div>
      ) : isEmptyUniverse ? (
        <div className="text-center p-20 border border-dashed border-brand-border rounded-2xl">
           <Inbox className="h-8 w-8 mx-auto text-brand-text-dim mb-4" />
           <p>No signals available.</p>
        </div>
      ) : isEmptySearch ? (
        <div className="text-center p-20 border border-dashed border-brand-border rounded-2xl">
           <Search className="h-8 w-8 mx-auto text-brand-text-dim mb-4" />
           <p>No matches found for "{searchTerm}".</p>
        </div>
      ) : (
        <div className="premium-glass-card rounded-2xl overflow-hidden border border-brand-border/50">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-white/5 border-b border-brand-border/50 text-[10px] font-mono uppercase tracking-widest text-brand-text-dim">
                  <th className="p-4 font-bold w-10 text-center">#</th>
                  <th className="p-4 font-bold cursor-pointer hover:text-white" onClick={() => handleSort('symbol')}>
                    <div className="flex items-center gap-1">Ticker <ArrowUpDown className="w-3 h-3"/></div>
                  </th>
                  <th className="p-4 font-bold">Company</th>
                  <th className="p-4 font-bold">Sector</th>
                  <th className="p-4 font-bold text-right cursor-pointer hover:text-white" onClick={() => handleSort('score')}>
                    <div className="flex items-center justify-end gap-1">Score <ArrowUpDown className="w-3 h-3"/></div>
                  </th>
                  <th className="p-4 font-bold text-right cursor-pointer hover:text-white" onClick={() => handleSort('mlRankScore')}>
                    <div className="flex items-center justify-end gap-1">ML Alpha <ArrowUpDown className="w-3 h-3"/></div>
                  </th>
                  <th className="p-4 font-bold text-right cursor-pointer hover:text-white" onClick={() => handleSort('roe')}>
                    <div className="flex items-center justify-end gap-1">ROE <ArrowUpDown className="w-3 h-3"/></div>
                  </th>
                  <th className="p-4 font-bold text-right cursor-pointer hover:text-white" onClick={() => handleSort('pe')}>
                    <div className="flex items-center justify-end gap-1">P/E <ArrowUpDown className="w-3 h-3"/></div>
                  </th>
                  <th className="p-4 font-bold text-right cursor-pointer hover:text-white" onClick={() => handleSort('fScore')}>
                    <div className="flex items-center justify-end gap-1">F-Score <ArrowUpDown className="w-3 h-3"/></div>
                  </th>
                  <th className="p-4 font-bold text-right cursor-pointer hover:text-white" onClick={() => handleSort('marketCapCr')}>
                     <div className="flex items-center justify-end gap-1">Mkt Cap <ArrowUpDown className="w-3 h-3"/></div>
                  </th>
                </tr>
              </thead>
              <tbody className="text-sm font-mono divide-y divide-brand-border/30">
                <AnimatePresence>
                  {sortedSignals.map((sig, idx) => {
                    const mlAlpha = Number(sig.raw?.ml_predicted_return ?? 0)
                    const fScore = (sig.raw?.f_score as number) ?? '-'
                    const marketCap = Number(sig.raw?.market_cap_cr ?? 0)
                    const roe = Number(sig.raw?.avg_roe_5y ?? 0)
                    const pe = Number(sig.raw?.pe_ratio ?? 0)

                    return (
                      <motion.tr 
                        key={sig.symbol}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="hover:bg-white/5 transition-colors"
                      >
                        <td className="p-4 text-center text-brand-text-dim text-xs font-bold">{idx + 1}</td>
                        <td className="p-4 font-bold text-brand-primary">{sig.symbol.replace('.NS', '')}</td>
                        <td className="p-4 text-brand-text truncate max-w-[200px]" title={sig.name}>{sig.name}</td>
                        <td className="p-4 text-brand-text-dim text-xs">{sig.sector}</td>
                        <td className="p-4 text-right font-black">{sig.score?.toFixed(1) || '-'}</td>
                        <td className="p-4 text-right text-brand-accent font-bold">
                          {mlAlpha > 0 ? `+${mlAlpha.toFixed(1)}` : mlAlpha ? mlAlpha.toFixed(1) : '-'}
                        </td>
                        <td className="p-4 text-right text-brand-text-dim">{roe ? `${roe.toFixed(1)}%` : '-'}</td>
                        <td className="p-4 text-right text-brand-text-dim">{pe ? pe.toFixed(1) : '-'}</td>
                        <td className="p-4 text-right text-brand-text-dim">{fScore}</td>
                        <td className="p-4 text-right text-brand-text-dim">{marketCap ? `${(marketCap / 1000).toFixed(1)}k` : '-'}</td>
                      </motion.tr>
                    )
                  })}
                </AnimatePresence>
              </tbody>
            </table>
          </div>
        </div>
      )}
    </main>
  )
}
