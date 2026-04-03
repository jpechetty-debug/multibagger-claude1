import { motion } from 'framer-motion'
import { TrendingUp } from 'lucide-react'

interface HeaderProps {
  regime?: string
  acceleration?: number
}

export function Header({ regime = 'BULLISH', acceleration = 0.3 }: HeaderProps) {
  return (
    <header className="p-8 pb-0 flex justify-between items-start">
      <motion.div 
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        className="flex flex-col gap-1"
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-brand-accent text-brand-bg rounded-lg flex items-center justify-center font-display font-bold text-xl select-none">Σ</div>
          <h1 className="font-display font-extrabold text-3xl tracking-tight">SOVEREIGN<span className="text-brand-accent ml-2">v9.5</span></h1>
        </div>
        <p className="font-mono text-[10px] text-brand-text-dim uppercase tracking-widest pl-1 font-bold">Institutional Quant Terminal</p>
      </motion.div>

      <motion.div 
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0 }}
        className="flex gap-4 items-center"
      >
        <div className="bg-brand-card/50 border border-brand-border px-4 py-2 rounded-xl flex items-center gap-4 group hover:border-brand-accent/30 transition-all">
          <div className="flex flex-col">
            <span className="text-[8px] text-brand-text-dim uppercase font-bold tracking-tighter">Market Regime</span>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono font-bold text-brand-accent">{regime}</span>
              <span className="text-[8px] text-brand-text-dim font-bold bg-white/5 px-1 rounded">ACCEL: {acceleration.toFixed(2)}</span>
            </div>
          </div>
          <div className="w-8 h-8 rounded-full border-2 border-brand-accent/20 flex items-center justify-center group-hover:scale-110 transition-transform">
            <TrendingUp className="w-4 h-4 text-brand-accent" />
          </div>
        </div>
      </motion.div>
    </header>
  )
}
