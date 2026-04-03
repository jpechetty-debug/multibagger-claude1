import { motion } from 'framer-motion'
import { SignalData } from '../../lib/api'

interface SignalCardProps {
  signal: SignalData
  index: number
}

export function SignalCard({ signal, index }: SignalCardProps) {
  const isHighConviction = signal.score > 85
  const isMultibagger = signal.action === 'BUY' && signal.score > 90

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.9, y: 30 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ 
        delay: 0.2 + index * 0.05, 
        type: 'spring', 
        stiffness: 200, 
        damping: 20 
      }}
      className={`brutalist-card p-6 group cursor-pointer transition-all duration-300 hover:border-brand-accent/50 group ${index % 3 === 0 ? 'mt-4' : 'mt-0'}`}
    >
      <div className="flex justify-between items-start mb-6">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-display font-extrabold text-2xl tracking-tight leading-none group-hover:text-brand-accent transition-colors">{signal.symbol}</h3>
            {isMultibagger && (
              <span className="w-2 h-2 rounded-full bg-brand-accent animate-ping" />
            )}
          </div>
          <p className="font-mono text-[9px] text-brand-text-dim uppercase mt-1.5 font-bold tracking-widest">{signal.sector}</p>
        </div>
        <div className={`px-2 py-1 rounded text-[10px] font-mono font-bold tracking-tighter shadow-sm border ${
          signal.action === 'BUY' ? 'bg-brand-accent/10 text-brand-accent border-brand-accent/20' : 
          signal.action === 'WATCH' ? 'bg-brand-gold/10 text-brand-gold border-brand-gold/20' : 
          'bg-white/5 text-brand-text-dim border-white/5'
        }`}>
          {signal.action}
        </div>
      </div>

      <div className="flex items-baseline gap-1 mb-8">
        <span className="text-xl font-display font-medium">₹{signal.price.toLocaleString('en-IN')}</span>
        <span className={`text-[10px] font-mono font-bold ${signal.change_pct >= 0 ? 'text-brand-accent' : 'text-brand-rose'}`}>
          {signal.change_pct >= 0 ? '+' : ''}{signal.change_pct.toFixed(2)}%
        </span>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex-1 h-[2px] bg-brand-bg rounded-full overflow-hidden">
          <motion.div 
            initial={{ width: 0 }}
            animate={{ width: signal.score + '%' }}
            className={`h-full ${isHighConviction ? 'bg-brand-accent' : 'bg-brand-gold'}`}
          />
        </div>
        <span className={`text-sm font-display font-black tracking-tighter ${isHighConviction ? 'text-brand-accent' : 'text-brand-gold'}`}>
          {Math.round(signal.score)}
        </span>
      </div>

      {/* Experimental Asymmetric Overlay */}
      <div className={`absolute -bottom-2 -right-2 w-12 h-12 rounded-full blur-xl transition-all duration-500 opacity-20 ${
        isHighConviction ? 'bg-brand-accent' : 'bg-brand-gold'
      }`} />
    </motion.div>
  )
}
