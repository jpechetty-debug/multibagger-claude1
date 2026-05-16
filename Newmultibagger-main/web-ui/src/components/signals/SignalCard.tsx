import { forwardRef } from 'react'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { ShieldCheck, ShieldAlert, Database } from 'lucide-react'

import type { SignalData } from '../../lib/contracts'

interface SignalCardProps {
  signal: SignalData
  index: number
}

export const SignalCard = forwardRef<HTMLDivElement, SignalCardProps>(function SignalCard(
  { signal, index },
  ref,
) {
  const navigate = useNavigate()
  const isHighConviction = signal.score > 85
  const isMultibagger = signal.action === 'BUY' && signal.score > 90
  const scoreWidth = Math.max(0, Math.min(signal.score, 100))
  
  const dq = signal.dataQuality ?? 100
  const isReliable = dq >= 90
  const hasFlags = (signal.dataQualityFlags ?? '').length > 0

  return (
    <motion.div
      ref={ref}
      onClick={() => navigate(`/stock/${signal.symbol}`)}
      layout
      initial={{ opacity: 0, scale: 0.9, y: 30 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{
        delay: 0.2 + index * 0.05,
        type: 'spring',
        stiffness: 200,
        damping: 20,
      }}
      className={`premium-glass-card p-6 group cursor-pointer transition-all duration-300 hover:border-brand-primary/50 ${index % 3 === 0 ? 'mt-4' : 'mt-0'}`}
    >
      <div className="mb-6 flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-display text-2xl font-extrabold tracking-tight leading-none transition-colors group-hover:text-brand-primary">
              {signal.symbol}
            </h3>
            {isMultibagger ? (
              <span className="h-2 w-2 rounded-full bg-brand-primary animate-ping" />
            ) : null}
          </div>
          <p className="mt-1.5 font-mono text-[10px] font-bold uppercase tracking-tight text-brand-text">
            {signal.name}
          </p>
          <p className="mt-1 font-mono text-[9px] font-bold uppercase tracking-widest text-brand-text-dim">
            {signal.sector}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
            <div
              className={`rounded border px-2 py-1 text-[10px] font-mono font-bold tracking-tighter shadow-sm ${
                signal.action === 'BUY'
                  ? 'border-brand-primary/20 bg-brand-primary/10 text-brand-primary'
                  : signal.action === 'WATCH'
                    ? 'border-brand-accent/20 bg-brand-accent/10 text-brand-accent'
                    : 'border-white/5 bg-white/5 text-brand-text-dim'
              }`}
            >
              {signal.action}
            </div>
            {hasFlags && (
                <div className="flex items-center gap-1 text-[8px] font-mono font-bold uppercase tracking-tighter text-brand-rose bg-brand-rose/10 px-1.5 py-0.5 rounded border border-brand-rose/20">
                    <ShieldAlert className="w-2.5 h-2.5" />
                    Audit Flagged
                </div>
            )}
        </div>
      </div>

      <div className="mb-8 flex items-baseline gap-1">
        <span className="font-display text-xl font-medium">
          Rs {signal.price.toLocaleString('en-IN')}
        </span>
        <span
          className={`text-[10px] font-mono font-bold ${
            signal.changePct >= 0 ? 'text-brand-emerald' : 'text-brand-rose'
          }`}
        >
          {signal.changePct >= 0 ? '+' : ''}
          {signal.changePct.toFixed(2)}%
        </span>
      </div>

      <div className="space-y-4">
          <div className="flex items-center gap-3">
            <div className="h-[2px] flex-1 overflow-hidden rounded-full bg-brand-bg">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${scoreWidth}%` }}
                className={`h-full ${isHighConviction ? 'bg-brand-primary' : 'bg-brand-accent'}`}
              />
            </div>
            <div className="flex items-baseline gap-1">
                <span
                className={`font-display text-sm font-black tracking-tighter ${
                    isHighConviction ? 'text-brand-primary' : 'text-brand-accent'
                }`}
                >
                {Math.round(signal.score)}
                </span>
                <span className="text-[8px] font-mono font-bold text-brand-text-dim uppercase">Score</span>
            </div>
          </div>

          <div className="flex items-center justify-between pt-2 border-t border-white/5">
            <div className="flex items-center gap-1.5">
                <div className={`p-1 rounded ${isReliable ? 'bg-brand-emerald/10 text-brand-emerald' : 'bg-brand-rose/10 text-brand-rose'}`}>
                    {isReliable ? <ShieldCheck className="w-3 h-3" /> : <ShieldAlert className="w-3 h-3" />}
                </div>
                <div>
                    <p className="text-[8px] font-mono font-bold uppercase tracking-widest text-brand-text-dim">Reliability</p>
                    <p className={`text-[10px] font-mono font-bold ${isReliable ? 'text-brand-emerald' : 'text-brand-rose'}`}>{dq}%</p>
                </div>
            </div>
            <div className="flex items-center gap-1.5 text-right">
                <div>
                    <p className="text-[8px] font-mono font-bold uppercase tracking-widest text-brand-text-dim">Source</p>
                    <p className="text-[10px] font-mono font-bold text-brand-text flex items-center gap-1 justify-end">
                        <Database className="w-2.5 h-2.5 opacity-50" />
                        Quant Engine
                    </p>
                </div>
            </div>
          </div>
      </div>

      <div
        className={`absolute -bottom-2 -right-2 h-12 w-12 rounded-full blur-xl opacity-20 transition-all duration-500 ${
          isHighConviction ? 'bg-brand-primary' : 'bg-brand-accent'
        }`}
      />
    </motion.div>
  )
})
