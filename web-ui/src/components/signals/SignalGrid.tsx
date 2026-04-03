import { SignalCard } from './SignalCard'
import { SignalData } from '../../lib/api'
import { motion, AnimatePresence } from 'framer-motion'
import { Heartbeat } from '../metrics/Heartbeat'
import { Search } from 'lucide-react'

interface SignalGridProps {
  signals: SignalData[]
  onSearch: (term: string) => void
}

export function SignalGrid({ signals, onSearch }: SignalGridProps) {
  return (
    <main className="p-8 pt-12">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 content-start items-start">
        
        {/* Metric Anchor: Heartbeat */}
        <Heartbeat />

        {/* Dynamic Signal Cards */}
        <AnimatePresence mode="popLayout">
          {signals.map((signal, idx) => (
            <SignalCard 
              key={signal.symbol} 
              signal={signal} 
              index={idx} 
            />
          ))}
        </AnimatePresence>

        {/* Tactical Search Card (Last element) */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
          className="brutalist-card p-6 h-full flex flex-col justify-center bg-brand-accent/5 border-dashed border-brand-accent/30 hover:border-brand-accent/50 transition-all group"
        >
          <div className="flex flex-col items-center gap-4 text-center">
            <div className="w-12 h-12 rounded-xl bg-brand-accent/10 flex items-center justify-center group-hover:scale-110 transition-transform">
              <Search className="w-6 h-6 text-brand-accent" />
            </div>
            <div>
              <h4 className="font-display font-bold text-lg">Scan Universe</h4>
              <p className="text-[10px] font-mono text-brand-text-dim text-wrap px-4 uppercase tracking-tighter mt-1 font-bold">Active institutional sweep across 500+ symbols</p>
            </div>
            <div className="mt-4 w-full relative">
              <input 
                type="text" 
                placeholder="PROMPT TICKER..."
                onChange={(e) => onSearch(e.target.value)}
                className="w-full bg-brand-bg border border-brand-border rounded-xl px-4 py-3 text-xs font-mono focus:border-brand-accent outline-none font-bold"
              />
            </div>
          </div>
        </motion.div>

      </div>
    </main>
  )
}
