import { useEffect, useState } from 'react'
import { Activity, Server, Zap, AlertCircle } from 'lucide-react'
import { api } from '../../lib/api'
import type { ProviderHealthItem } from '../../lib/contracts'
import { motion } from 'framer-motion'

const STATUS_CONFIG: Record<string, { color: string, icon: any, label: string }> = {
  healthy: { color: 'text-brand-accent', icon: Zap, label: 'OPERATIONAL' },
  degraded: { color: 'text-brand-gold', icon: AlertCircle, label: 'DEGRADED' },
  down: { color: 'text-brand-rose', icon: Server, label: 'OFFLINE' },
  unknown: { color: 'text-brand-text-dim', icon: Activity, label: 'UNKNOWN' },
}

export function ProviderHealthPanel() {
  const [providers, setProviders] = useState<ProviderHealthItem[]>([])

  useEffect(() => {
    api.getProviderHealth().then(r => setProviders(r.providers)).catch(() => {})
  }, [])

  if (providers.length === 0) return null

  return (
    <div className="bg-brand-card/40 border border-white/5 rounded-2xl p-6 relative overflow-hidden group">
      {/* Background Glow */}
      <div className="absolute top-0 right-0 w-32 h-32 bg-brand-accent/5 blur-[60px] group-hover:bg-brand-accent/10 transition-colors pointer-events-none" />
      
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-brand-accent/10 rounded-lg">
            <Activity className="h-4 w-4 text-brand-accent" />
          </div>
          <h3 className="text-xs font-black uppercase tracking-[0.2em] text-white">
            Data Source Health
          </h3>
        </div>
        <div className="text-[10px] font-mono text-brand-text-dim flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-brand-accent animate-pulse" />
          LIVE TELEMETRY
        </div>
      </div>

      <div className="space-y-6">
        {providers.map((p, idx) => {
          const config = STATUS_CONFIG[p.status] ?? STATUS_CONFIG.unknown
          const StatusIcon = config.icon
          
          return (
            <motion.div 
              key={p.name}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: idx * 0.1 }}
              className="space-y-3"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-black uppercase tracking-wider text-white italic">
                    {p.name}
                  </span>
                  <StatusIcon className={`w-3 h-3 ${config.color}`} />
                </div>
                <div className="flex items-center gap-3">
                  <span className={`text-[10px] font-mono font-bold ${config.color}`}>
                    {config.label}
                  </span>
                  <span className="text-xs font-mono font-black text-white">
                    {p.success_rate.toFixed(1)}%
                  </span>
                </div>
              </div>

              <div className="relative h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.max(2, p.success_rate)}%` }}
                  transition={{ duration: 1, ease: "easeOut", delay: idx * 0.1 + 0.5 }}
                  className={`absolute top-0 left-0 h-full rounded-full ${
                    p.status === 'healthy' ? 'bg-brand-accent shadow-[0_0_10px_rgba(34,211,238,0.3)]' :
                    p.status === 'degraded' ? 'bg-brand-gold' : 'bg-brand-rose'
                  }`}
                />
              </div>

              <div className="flex justify-between items-center text-[9px] font-bold uppercase tracking-widest text-brand-text-dim/60">
                <div className="flex items-center gap-1.5">
                  <Server className="w-2.5 h-2.5" />
                  {p.total_calls.toLocaleString()} REQUESTS
                </div>
                {p.last_success && (
                  <div className="flex items-center gap-1.5">
                    <Zap className="w-2.5 h-2.5 text-brand-accent" />
                    LATEST: {new Date(p.last_success).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </div>
                )}
              </div>
            </motion.div>
          )
        })}
      </div>
      
      <div className="mt-6 pt-4 border-t border-white/5">
        <p className="text-[9px] text-brand-text-dim leading-relaxed font-medium">
          <span className="text-brand-accent">NOTE:</span> SYSTEM AUTOMATICALLY SWITCHES TO FAILOVER NODES IF PRIMARY LATENCY EXCEEDS 2500MS.
        </p>
      </div>
    </div>
  )
}
