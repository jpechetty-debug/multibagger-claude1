import { Activity } from 'lucide-react'
import { motion } from 'framer-motion'
import { useState, useEffect } from 'react'

export function Heartbeat() {
  const [latency, setLatency] = useState(14.2)
  
  useEffect(() => {
    const i = setInterval(() => {
      setLatency(12 + Math.random() * 4)
    }, 2000)
    return () => clearInterval(i)
  }, [])

  return (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 }}
      className="brutalist-card p-6 h-full border-l-4 border-l-brand-accent flex flex-col justify-between group hover:border-l-brand-accent/80 transition-all"
    >
      <div>
        <div className="flex justify-between items-center mb-4">
          <span className="text-[10px] font-mono text-brand-text-dim uppercase font-bold tracking-widest">Neural Heartbeat</span>
          <Activity className="w-4 h-4 text-brand-accent animate-pulse" />
        </div>
        <div className="flex items-baseline gap-2">
          <span className="text-5xl font-display font-black tracking-tighter">{latency.toFixed(1)}</span>
          <span className="text-sm font-mono text-brand-text-dim font-bold">ms</span>
        </div>
      </div>
      <div className="mt-8">
        <div className="h-1 w-full bg-brand-bg rounded-full overflow-hidden">
          <motion.div 
            initial={{ width: 0 }}
            animate={{ width: '100%' }}
            className="h-full bg-brand-accent shadow-[0_0_10px_rgba(0,255,163,0.5)]"
          />
        </div>
        <div className="flex justify-between mt-2 font-mono text-[9px] uppercase font-bold text-brand-text-dim">
          <span>P99 Integrity</span>
          <span className="text-brand-accent">99.9%</span>
        </div>
      </div>
    </motion.div>
  )
}
