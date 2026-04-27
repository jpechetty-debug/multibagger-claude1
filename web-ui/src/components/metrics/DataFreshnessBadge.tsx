import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle, Clock, Zap } from 'lucide-react'
import { api } from '../../lib/api'
import type { DataFreshnessResponse } from '../../lib/contracts'

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
      <div
        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-mono font-bold uppercase tracking-widest cursor-help transition-all ${config.bg} ${config.color}`}
      >
        <Icon className={`h-3 w-3 ${config.pulse ? 'animate-pulse' : ''}`} />
        {config.label}
        <span className="opacity-60">{data.age_days}d</span>
      </div>

      {showTooltip && (
        <div className="absolute top-full mt-2 right-0 z-50 w-72 rounded-xl border border-brand-border bg-brand-card p-4 shadow-2xl text-xs font-mono">
          <div className="space-y-2">
            <div className="flex justify-between">
              <span className="text-brand-text-dim">Latest Data</span>
              <span className="text-brand-text font-bold">{data.latest_as_of_date ?? 'N/A'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-brand-text-dim">Age</span>
              <span className={`font-bold ${config.color}`}>{data.age_days} days</span>
            </div>
            <div className="flex justify-between">
              <span className="text-brand-text-dim">Data Quality</span>
              <span className="text-brand-text font-bold">{data.data_quality}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-brand-text-dim">Refresh Status</span>
              <span className={`font-bold ${data.scheduled_refresh.status === 'recent' ? 'text-brand-accent' : 'text-brand-rose'}`}>
                {data.scheduled_refresh.status?.toUpperCase()}
              </span>
            </div>
            {data.scheduled_refresh.age_hours != null && (
              <div className="flex justify-between">
                <span className="text-brand-text-dim">Last Scan</span>
                <span className="text-brand-text">{data.scheduled_refresh.age_hours}h ago</span>
              </div>
            )}
          </div>
          {data.status === 'EXPIRED' && (
            <div className="mt-3 p-2 rounded bg-brand-rose/10 border border-brand-rose/20 text-brand-rose">
              ⚠ BUY signals are blocked on expired data. Run a fresh scan.
            </div>
          )}
        </div>
      )}
    </div>
  )
}
