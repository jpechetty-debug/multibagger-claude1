import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Activity } from 'lucide-react'

import { api } from '../../lib/api'

export function Heartbeat() {
  const [latency, setLatency] = useState<number | null>(null)
  const [isHealthy, setIsHealthy] = useState(true)

  useEffect(() => {
    let isCancelled = false

    const checkLatency = async () => {
      const start = performance.now()
      try {
        await api.getHealth()
        const end = performance.now()
        if (!isCancelled) {
          setLatency(Math.round(end - start))
          setIsHealthy(true)
        }
      } catch {
        if (!isCancelled) {
          setLatency(null)
          setIsHealthy(false)
        }
      }
    }

    void checkLatency()
    const interval = setInterval(() => {
      void checkLatency()
    }, 5000)

    return () => {
      isCancelled = true
      clearInterval(interval)
    }
  }, [])

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 }}
      className="brutalist-card flex h-full flex-col justify-between border-l-4 border-l-brand-accent p-6 transition-all group hover:border-l-brand-accent/80"
    >
      <div>
        <div className="mb-4 flex items-center justify-between">
          <span className="text-[10px] font-mono font-bold uppercase tracking-widest text-brand-text-dim">
            Neural Heartbeat
          </span>
          <Activity
            className={`h-4 w-4 ${isHealthy ? 'animate-pulse text-brand-accent' : 'text-brand-rose'}`}
          />
        </div>
        <div className="flex items-baseline gap-2">
          <span className="font-display text-5xl font-black tracking-tighter">
            {latency === null ? '--' : latency.toFixed(1)}
          </span>
          <span className="text-sm font-mono font-bold text-brand-text-dim">ms</span>
        </div>
      </div>
      <div className="mt-8">
        <div className="h-1 w-full overflow-hidden rounded-full bg-brand-bg">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: isHealthy ? '100%' : '35%' }}
            className={`h-full ${isHealthy ? 'bg-brand-accent shadow-[0_0_10px_rgba(0,255,163,0.5)]' : 'bg-brand-rose'}`}
          />
        </div>
        <div className="mt-2 flex justify-between font-mono text-[9px] font-bold uppercase text-brand-text-dim">
          <span>{isHealthy ? 'Feed Integrity' : 'Feed Degraded'}</span>
          <span className={isHealthy ? 'text-brand-accent' : 'text-brand-rose'}>
            {isHealthy ? 'Online' : 'Retrying'}
          </span>
        </div>
      </div>
    </motion.div>
  )
}
