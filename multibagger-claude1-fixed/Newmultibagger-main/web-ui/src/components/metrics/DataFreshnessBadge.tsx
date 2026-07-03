import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle, Clock, Zap, Activity, Info } from 'lucide-react'
import { api } from '../../lib/api'
import type { DataFreshnessResponse } from '../../lib/contracts'
import { motion, AnimatePresence } from 'framer-motion'

const STATUS_CONFIG = {
  FRESH: {
    icon: CheckCircle,
    color: 'text-brand-accent',
    bg: 'bg-brand-accent/10 border-brand-accent/20',
    label: 'FRESH',
    pulse: false,
  },
  STALE: {
    icon: Clock,
    color: 'text-brand-gold',
    bg: 'bg-brand-gold/10 border-brand-gold/20',
    label: 'STALE',
    pulse: true,
  },
  EXPIRED: {
    icon: AlertTriangle,
    color: 'text-brand-rose',
    bg: 'bg-brand-rose/10 border-brand-rose/20',
    label: 'EXPIRED',
    pulse: true,
  },
  UNKNOWN: {
    icon: Zap,
    color: 'text-brand-text-dim',
    bg: 'bg-white/5 border-white/10',
    label: 'UNKNOWN',
    pulse: false,
  },
} as const

export function DataFreshnessBadge() {
  const [data, setData] = useState<DataFreshnessResponse | null>(null)
  const [showTooltip, setShowTooltip] = useState(false)

  useEffect(() => {
    api.getDataFreshness().then(setData).catch(() => {})
    const interval = setInterval(() => {
      api.getDataFreshness().then(setData).catch(() => {})
    }, 60_000)
    return () => clearInterval(interval)
  }, [])

  if (!data) return null

  const config = STATUS_CONFIG[data.status] ?? STATUS_CONFIG.UNKNOWN
  const Icon = config.icon

  return (
    <div
      className="relative"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <motion.div
        layout
        className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[10px] font-mono font-black uppercase tracking-[0.1em] cursor-help transition-all duration-300 ${config.bg} ${config.color}`}
      >
        <Icon className={`h-3 w-3 ${config.pulse ? 'animate-pulse' : ''}`} />
        {config.label}
        <span className="opacity-40 font-normal">[{data.age_days}D]</span>
      </motion.div>

      <AnimatePresence>
        {showTooltip && (
          <motion.div 
            initial={{ opacity: 0, y: 10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.95 }}
            className="absolute top-full mt-3 right-0 z-50 w-80 rounded-2xl border border-white/10 bg-brand-card/95 backdrop-blur-xl p-5 shadow-[0_20px_50px_rgba(0,0,0,0.5)] overflow-hidden"
          >
            {/* Background Decorative Element */}
            <div className="absolute top-0 right-0 w-32 h-32 bg-brand-accent/5 blur-3xl -z-10" />
            
            <div className="flex items-center gap-2 mb-4 pb-3 border-b border-white/5">
              <Activity className="w-4 h-4 text-brand-accent" />
              <span className="text-[10px] font-black uppercase tracking-[0.2em] text-white">System Data Intelligence</span>
            </div>

            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-[10px] text-brand-text-dim uppercase font-bold tracking-wider">Latest Snapshot</span>
                <span className="text-xs font-mono text-white font-bold">{data.latest_as_of_date ?? 'N/A'}</span>
              </div>
              
              <div className="flex justify-between items-center">
                <span className="text-[10px] text-brand-text-dim uppercase font-bold tracking-wider">Data Integrity</span>
                <div className="flex items-center gap-2">
                   <div className="w-16 h-1 bg-white/5 rounded-full overflow-hidden">
                     <div className="h-full bg-brand-accent" style={{ width: `${data.data_quality}%` }} />
                   </div>
                   <span className="text-xs font-mono text-brand-accent font-bold">{data.data_quality}%</span>
                </div>
              </div>

              <div className="pt-3 pb-2 border-t border-white/5">
                <div className="text-[9px] text-brand-text-dim font-black uppercase tracking-[0.2em] mb-3">Universe Breakdown</div>
                <div className="grid grid-cols-4 gap-2">
                  <div className="text-center">
                    <div className="text-[8px] text-brand-text-dim mb-1 uppercase">Fresh</div>
                    <div className="text-xs font-mono font-bold text-brand-accent">{data.universe_counts.fresh}</div>
                  </div>
                  <div className="text-center">
                    <div className="text-[8px] text-brand-text-dim mb-1 uppercase">Stale</div>
                    <div className="text-xs font-mono font-bold text-brand-gold">{data.universe_counts.stale}</div>
                  </div>
                  <div className="text-center">
                    <div className="text-[8px] text-brand-text-dim mb-1 uppercase">Exp.</div>
                    <div className="text-xs font-mono font-bold text-brand-rose">{data.universe_counts.expired}</div>
                  </div>
                  <div className="text-center">
                    <div className="text-[8px] text-brand-text-dim mb-1 uppercase">Inc.</div>
                    <div className="text-xs font-mono font-bold text-white/40">{data.universe_counts.incomplete}</div>
                  </div>
                </div>
              </div>

              <div className="flex justify-between items-center pt-2">
                <span className="text-[10px] text-brand-text-dim uppercase font-bold tracking-wider">Scheduled Scan</span>
                <span className={`text-[10px] font-black uppercase px-2 py-0.5 rounded ${data.scheduled_refresh.status === 'recent' ? 'bg-brand-accent/10 text-brand-accent' : 'bg-brand-rose/10 text-brand-rose'}`}>
                  {data.scheduled_refresh.status}
                </span>
              </div>
            </div>

            {data.status === 'EXPIRED' && (
              <motion.div 
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                className="mt-4 p-3 rounded-xl bg-brand-rose/10 border border-brand-rose/20 text-[9px] text-brand-rose font-bold leading-relaxed flex gap-2"
              >
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span>BUY SIGNALS BLOCKED DUE TO DATA EXPIRATION. RE-RUN SCANNER IMMEDIATELY.</span>
              </motion.div>
            )}
            
            <div className="mt-4 pt-3 border-t border-white/5 flex items-center gap-2 text-[8px] text-brand-text-dim font-bold uppercase italic">
              <Info className="w-3 h-3" />
              Source: {data.source}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
