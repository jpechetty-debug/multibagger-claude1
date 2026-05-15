import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Activity, ShieldCheck, Zap } from 'lucide-react'

import { api } from '../../lib/api'
import { type SwarmStatusResponse, type SwarmAlert } from '../../lib/contracts'

export function Heartbeat() {
  const [latency, setLatency] = useState<number | null>(null)
  const [isHealthy, setIsHealthy] = useState(true)
  const [swarmStatus, setSwarmStatus] = useState<SwarmStatusResponse | null>(null)
  const [recentAlert, setRecentAlert] = useState<SwarmAlert | null>(null)

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

    const checkSwarm = async () => {
      try {
        const [status, alerts] = await Promise.all([
          api.getSwarmStatus(),
          api.getSwarmAlerts()
        ])
        if (!isCancelled) {
          setSwarmStatus(status)
          if (alerts.length > 0) setRecentAlert(alerts[0])
        }
      } catch (err) {
        console.error("Swarm check failed", err)
      }
    }

    void checkLatency()
    void checkSwarm()
    const interval = setInterval(() => {
      void checkLatency()
      void checkSwarm()
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

      {/* Swarm Intelligence Overlay */}
      <div className="mt-6 border-t border-brand-bg pt-4">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <ShieldCheck className={`h-3 w-3 ${swarmStatus?.status === 'online' ? 'text-brand-accent' : 'text-brand-text-dim'}`} />
            <span className="text-[9px] font-mono font-bold uppercase text-brand-text-dim">
              Swarm: {swarmStatus?.status || 'offline'}
            </span>
          </div>
          {swarmStatus?.active_agents && (
            <span className="text-[9px] font-mono text-brand-accent">
              {swarmStatus.active_agents} AGENTS
            </span>
          )}
        </div>
        
        {recentAlert ? (
          <div className="rounded border border-brand-accent/20 bg-brand-accent/5 p-2">
            <div className="flex items-center gap-2">
              <Zap className="h-3 w-3 text-brand-accent" />
              <span className="text-[10px] font-bold text-brand-accent uppercase">
                {recentAlert.type}
              </span>
            </div>
            <p className="mt-1 text-[9px] leading-tight text-brand-text line-clamp-2">
              {recentAlert.message}
            </p>
          </div>
        ) : (
          <div className="text-[9px] font-mono text-brand-text-dim italic">
            Waiting for regime signals...
          </div>
        )}
      </div>

    </motion.div>
  )
}
