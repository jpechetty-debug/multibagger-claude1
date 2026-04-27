import { useEffect, useState } from 'react'
import { Activity } from 'lucide-react'
import { api } from '../../lib/api'
import type { ProviderHealthItem } from '../../lib/contracts'

const STATUS_COLORS: Record<string, string> = {
  healthy: 'bg-brand-accent',
  degraded: 'bg-brand-gold',
  down: 'bg-brand-rose',
  unknown: 'bg-white/20',
}

export function ProviderHealthPanel() {
  const [providers, setProviders] = useState<ProviderHealthItem[]>([])

  useEffect(() => {
    api.getProviderHealth().then(r => setProviders(r.providers)).catch(() => {})
  }, [])

  if (providers.length === 0) return null

  return (
    <div className="brutalist-card p-5">
      <div className="flex items-center gap-2 mb-4">
        <Activity className="h-4 w-4 text-brand-accent" />
        <h3 className="font-mono text-xs font-bold uppercase tracking-widest text-brand-text-dim">
          Provider Health
        </h3>
      </div>

      <div className="space-y-3">
        {providers.map((p) => {
          const barColor = STATUS_COLORS[p.status] ?? STATUS_COLORS.unknown
          return (
            <div key={p.name} className="space-y-1">
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs font-bold uppercase tracking-tight text-brand-text">
                  {p.name}
                </span>
                <span className={`font-mono text-[10px] font-bold uppercase tracking-widest ${
                  p.status === 'healthy' ? 'text-brand-accent' :
                  p.status === 'degraded' ? 'text-brand-gold' : 'text-brand-rose'
                }`}>
                  {p.success_rate.toFixed(0)}%
                </span>
              </div>
              <div className="h-1.5 w-full rounded-full bg-white/5 overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-700 ${barColor}`}
                  style={{ width: `${Math.max(2, p.success_rate)}%` }}
                />
              </div>
              <div className="flex justify-between text-[9px] font-mono text-brand-text-dim">
                <span>{p.total_calls} calls</span>
                <span>{p.status}</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
