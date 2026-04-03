import { forwardRef } from 'react'
import { motion } from 'framer-motion'

import type { SignalData } from '../../lib/contracts'

interface SignalCardProps {
  signal: SignalData
  index: number
}

export const SignalCard = forwardRef<HTMLDivElement, SignalCardProps>(function SignalCard(
  { signal, index },
  ref,
) {
  const isHighConviction = signal.score > 85
  const isMultibagger = signal.action === 'BUY' && signal.score > 90
  const scoreWidth = Math.max(0, Math.min(signal.score, 100))

  return (
    <motion.div
      ref={ref}
      layout
      initial={{ opacity: 0, scale: 0.9, y: 30 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{
        delay: 0.2 + index * 0.05,
        type: 'spring',
        stiffness: 200,
        damping: 20,
      }}
      className={`brutalist-card p-6 group cursor-pointer transition-all duration-300 hover:border-brand-accent/50 ${index % 3 === 0 ? 'mt-4' : 'mt-0'}`}
    >
      <div className="mb-6 flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-display text-2xl font-extrabold tracking-tight leading-none transition-colors group-hover:text-brand-accent">
              {signal.symbol}
            </h3>
            {isMultibagger ? (
              <span className="h-2 w-2 rounded-full bg-brand-accent animate-ping" />
            ) : null}
          </div>
          <p className="mt-1.5 font-mono text-[10px] font-bold uppercase tracking-tight text-brand-text">
            {signal.name}
          </p>
          <p className="mt-1 font-mono text-[9px] font-bold uppercase tracking-widest text-brand-text-dim">
            {signal.sector}
          </p>
        </div>
        <div
          className={`rounded border px-2 py-1 text-[10px] font-mono font-bold tracking-tighter shadow-sm ${
            signal.action === 'BUY'
              ? 'border-brand-accent/20 bg-brand-accent/10 text-brand-accent'
              : signal.action === 'WATCH'
                ? 'border-brand-gold/20 bg-brand-gold/10 text-brand-gold'
                : 'border-white/5 bg-white/5 text-brand-text-dim'
          }`}
        >
          {signal.action}
        </div>
      </div>

      <div className="mb-8 flex items-baseline gap-1">
        <span className="font-display text-xl font-medium">
          Rs {signal.price.toLocaleString('en-IN')}
        </span>
        <span
          className={`text-[10px] font-mono font-bold ${
            signal.changePct >= 0 ? 'text-brand-accent' : 'text-brand-rose'
          }`}
        >
          {signal.changePct >= 0 ? '+' : ''}
          {signal.changePct.toFixed(2)}%
        </span>
      </div>

      <div className="flex items-center gap-3">
        <div className="h-[2px] flex-1 overflow-hidden rounded-full bg-brand-bg">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${scoreWidth}%` }}
            className={`h-full ${isHighConviction ? 'bg-brand-accent' : 'bg-brand-gold'}`}
          />
        </div>
        <span
          className={`font-display text-sm font-black tracking-tighter ${
            isHighConviction ? 'text-brand-accent' : 'text-brand-gold'
          }`}
        >
          {Math.round(signal.score)}
        </span>
      </div>

      <div
        className={`absolute -bottom-2 -right-2 h-12 w-12 rounded-full blur-xl opacity-20 transition-all duration-500 ${
          isHighConviction ? 'bg-brand-accent' : 'bg-brand-gold'
        }`}
      />
    </motion.div>
  )
})
