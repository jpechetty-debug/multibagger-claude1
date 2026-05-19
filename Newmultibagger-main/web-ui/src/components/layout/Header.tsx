import { motion } from 'framer-motion'
import { TrendingUp, Heart, BarChart3 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { DataFreshnessBadge } from '../metrics/DataFreshnessBadge'
import { useWatchlist } from '../../lib/useWatchlist'

interface HeaderProps {
  regime?: string
  acceleration?: number
  isForced?: boolean
  isStale?: boolean
  lastUpdated?: string | null
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return 'Sync pending'
  }

  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }

  return parsed.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export function Header({
  regime = 'UNKNOWN',
  acceleration = 0,
  isForced = false,
  isStale = false,
  lastUpdated,
}: HeaderProps) {
  return (
    <header className="p-8 pb-0 flex justify-between items-start gap-6 flex-col lg:flex-row">
      <motion.div
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        className="flex flex-col gap-1"
      >
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 select-none items-center justify-center rounded-lg bg-brand-primary font-display text-xl font-bold text-brand-bg">
            S
          </div>
          <h1 className="font-display text-3xl font-extrabold tracking-tight">
            SOVEREIGN
            <span className="ml-2 text-brand-primary">v9.5</span>
          </h1>
        </div>
        <p className="pl-1 font-mono text-[10px] font-bold uppercase tracking-widest text-brand-text-dim">
          Institutional Quant Terminal
        </p>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0 }}
        className="flex gap-4 items-center"
      >
        <div className="group flex items-center gap-4 rounded-xl border border-brand-border bg-brand-card/30 backdrop-blur-md px-4 py-3 transition-all hover:border-brand-primary/30">
          <div className="flex flex-col gap-2">
            <span className="text-[8px] font-bold uppercase tracking-tighter text-brand-text-dim">
              Market Regime
            </span>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono font-bold text-brand-primary">{regime}</span>
              <span className="rounded bg-white/5 px-1 text-[8px] font-bold text-brand-text-dim">
                ACCEL: {acceleration.toFixed(2)}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-[8px] font-mono font-bold uppercase tracking-widest text-brand-text-dim">
              <span>Sync {formatTimestamp(lastUpdated)}</span>
              {isForced ? (
                <span className="rounded bg-brand-accent/10 px-1.5 py-0.5 text-brand-accent">
                  Forced
                </span>
              ) : null}
              {isStale ? (
                <span className="rounded bg-brand-rose/10 px-1.5 py-0.5 text-brand-rose">
                  Stale
                </span>
              ) : null}
            </div>
          </div>
          <div className="flex h-8 w-8 items-center justify-center rounded-full border-2 border-brand-primary/20 transition-transform group-hover:scale-110">
            <TrendingUp className="h-4 w-4 text-brand-primary" />
          </div>
        </div>

        <DataFreshnessBadge />

        <HeaderNavLinks />
      </motion.div>
    </header>
  )
}

function HeaderNavLinks() {
  const { count } = useWatchlist()
  return (
    <div className="flex items-center gap-2">
      <Link
        to="/watchlist"
        className="inline-flex items-center gap-1.5 rounded-lg border border-brand-border px-2.5 py-1.5 text-[10px] font-mono font-bold uppercase tracking-widest text-brand-text-dim hover:border-brand-primary/40 hover:text-brand-primary transition-colors touch-target"
      >
        <Heart className="h-3 w-3" />
        {count > 0 && <span className="text-brand-primary">{count}</span>}
      </Link>
      <Link
        to="/score-report"
        className="inline-flex items-center gap-1.5 rounded-lg border border-brand-border px-2.5 py-1.5 text-[10px] font-mono font-bold uppercase tracking-widest text-brand-text-dim hover:border-brand-primary/40 hover:text-brand-primary transition-colors touch-target"
      >
        <BarChart3 className="h-3 w-3" />
      </Link>
    </div>
  )
}
