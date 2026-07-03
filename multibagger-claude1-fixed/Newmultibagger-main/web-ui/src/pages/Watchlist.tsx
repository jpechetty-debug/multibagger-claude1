import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Heart, Trash2, ArrowLeft, AlertTriangle } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { api } from '../lib/api'
import type { SignalData } from '../lib/contracts'
import { useWatchlist } from '../lib/useWatchlist'
import { WatchlistSkeleton } from '../components/ui/Skeleton'

export function Watchlist() {
  const { watchlist, removeFromWatchlist, clearWatchlist } = useWatchlist()
  const [stocks, setStocks] = useState<SignalData[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (watchlist.length === 0) {
      setStocks([])
      setLoading(false)
      return
    }

    setLoading(true)
    api.getStocks()
      .then((all) => {
        const matched = all.filter(s => watchlist.includes(s.symbol))
        setStocks(matched)
      })
      .catch(() => setStocks([]))
      .finally(() => setLoading(false))
  }, [watchlist])

  return (
    <div className="min-h-screen bg-brand-bg text-brand-text p-4 md:p-8 pb-32">
      <div className="flex items-center gap-4 mb-8">
        <Link
          to="/"
          className="inline-flex items-center gap-2 font-mono text-sm tracking-widest text-brand-text-dim hover:text-brand-accent transition-colors uppercase touch-target"
        >
          <ArrowLeft size={16} />
          Dashboard
        </Link>
        <div className="flex-1" />
        {watchlist.length > 0 && (
          <button
            type="button"
            onClick={clearWatchlist}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-brand-rose/30 text-xs font-mono font-bold uppercase tracking-widest text-brand-rose hover:bg-brand-rose/10 transition-colors touch-target"
          >
            <Trash2 size={12} />
            Clear All
          </button>
        )}
      </div>

      <div className="brutalist-card p-6 md:p-8 mb-8 border-l-4 border-l-brand-accent">
        <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-brand-text-dim font-bold">
          Personal Watchlist
        </p>
        <h1 className="font-display text-3xl font-black tracking-tight mt-1">
          Tracked Convictions
        </h1>
        <p className="text-sm text-brand-text-dim mt-2">
          {watchlist.length} {watchlist.length === 1 ? 'stock' : 'stocks'} in your watchlist.
          These persist in your browser across sessions.
        </p>
      </div>

      {loading && (
        <WatchlistSkeleton />
      )}

      {!loading && watchlist.length === 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="brutalist-card p-12 border-dashed border-brand-border flex flex-col items-center justify-center gap-4 text-center"
        >
          <Heart className="h-12 w-12 text-brand-text-dim" />
          <h3 className="font-display text-2xl font-black">No Stocks Tracked</h3>
          <p className="text-sm text-brand-text-dim max-w-md">
            Visit any stock's detail page and click the Watch button to add it here.
          </p>
          <Link
            to="/"
            className="mt-4 inline-flex items-center gap-2 rounded-xl border border-brand-accent/30 bg-brand-accent/10 px-4 py-2 text-xs font-mono font-bold uppercase tracking-widest text-brand-accent hover:bg-brand-accent/20 transition-colors touch-target"
          >
            Browse Signals
          </Link>
        </motion.div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <AnimatePresence mode="popLayout">
          {stocks.map((stock, index) => {
            const isHighConviction = stock.score > 85
            return (
              <motion.div
                key={stock.symbol}
                layout
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                transition={{ delay: index * 0.05 }}
                className="brutalist-card p-6 group"
              >
                <div className="flex items-start justify-between mb-4">
                  <Link to={`/stock/${stock.symbol}`} className="hover:text-brand-accent transition-colors">
                    <h3 className="font-display text-2xl font-extrabold tracking-tight">{stock.symbol}</h3>
                    <p className="font-mono text-[10px] font-bold uppercase text-brand-text-dim mt-1">{stock.name}</p>
                  </Link>
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 text-[10px] font-mono font-bold rounded border ${
                      stock.action === 'BUY' ? 'border-brand-accent/20 bg-brand-accent/10 text-brand-accent' :
                      stock.action === 'WATCH' ? 'border-brand-gold/20 bg-brand-gold/10 text-brand-gold' :
                      'border-white/5 bg-white/5 text-brand-text-dim'
                    }`}>
                      {stock.action}
                    </span>
                    <button
                      type="button"
                      onClick={() => removeFromWatchlist(stock.symbol)}
                      className="p-1 rounded hover:bg-brand-rose/10 text-brand-text-dim hover:text-brand-rose transition-colors touch-target"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>

                <div className="flex items-baseline gap-2 mb-4">
                  <span className="font-display text-xl font-medium">
                    Rs {stock.price.toLocaleString('en-IN')}
                  </span>
                  <span className={`text-[10px] font-mono font-bold ${stock.changePct >= 0 ? 'text-brand-accent' : 'text-brand-rose'}`}>
                    {stock.changePct >= 0 ? '+' : ''}{stock.changePct.toFixed(2)}%
                  </span>
                </div>

                <div className="flex items-center gap-3">
                  <div className="h-[2px] flex-1 overflow-hidden rounded-full bg-brand-bg">
                    <div
                      className={`h-full ${isHighConviction ? 'bg-brand-accent' : 'bg-brand-gold'}`}
                      style={{ width: `${Math.min(stock.score, 100)}%` }}
                    />
                  </div>
                  <span className={`font-display text-sm font-black tracking-tighter ${
                    isHighConviction ? 'text-brand-accent' : 'text-brand-gold'
                  }`}>
                    {Math.round(stock.score)}
                  </span>
                </div>
              </motion.div>
            )
          })}
        </AnimatePresence>

        {/* Orphaned watchlist items (symbol saved but not in current universe) */}
        {!loading && watchlist.length > stocks.length && (
          <div className="brutalist-card p-5 border-dashed border-brand-border">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="h-4 w-4 text-brand-gold" />
              <span className="font-mono text-xs font-bold uppercase text-brand-gold">Orphaned</span>
            </div>
            <p className="text-xs text-brand-text-dim mb-3">
              {watchlist.length - stocks.length} watchlisted {watchlist.length - stocks.length === 1 ? 'symbol' : 'symbols'} not found in the current signal universe.
            </p>
            <div className="flex flex-wrap gap-1">
              {watchlist
                .filter(sym => !stocks.find(s => s.symbol === sym))
                .map(sym => (
                  <span key={sym} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-white/5 text-[10px] font-mono text-brand-text-dim">
                    {sym}
                    <button type="button" onClick={() => removeFromWatchlist(sym)} className="hover:text-brand-rose">×</button>
                  </span>
                ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
