import { motion } from 'framer-motion'
import { TrendingUp } from 'lucide-react'

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
          <div className="flex h-10 w-10 select-none items-center justify-center rounded-lg bg-brand-accent font-display text-xl font-bold text-brand-bg">
            S
          </div>
          <h1 className="font-display text-3xl font-extrabold tracking-tight">
            SOVEREIGN
            <span className="ml-2 text-brand-accent">v9.5</span>
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
        <div className="group flex items-center gap-4 rounded-xl border border-brand-border bg-brand-card/50 px-4 py-3 transition-all hover:border-brand-accent/30">
          <div className="flex flex-col gap-2">
            <span className="text-[8px] font-bold uppercase tracking-tighter text-brand-text-dim">
              Market Regime
            </span>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono font-bold text-brand-accent">{regime}</span>
              <span className="rounded bg-white/5 px-1 text-[8px] font-bold text-brand-text-dim">
                ACCEL: {acceleration.toFixed(2)}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-[8px] font-mono font-bold uppercase tracking-widest text-brand-text-dim">
              <span>Sync {formatTimestamp(lastUpdated)}</span>
              {isForced ? (
                <span className="rounded bg-brand-gold/10 px-1.5 py-0.5 text-brand-gold">
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
          <div className="flex h-8 w-8 items-center justify-center rounded-full border-2 border-brand-accent/20 transition-transform group-hover:scale-110">
            <TrendingUp className="h-4 w-4 text-brand-accent" />
          </div>
        </div>
      </motion.div>
    </header>
  )
}
