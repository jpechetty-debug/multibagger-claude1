import React, { useEffect, useState } from 'react'
import { TrendingUp, BarChart3, Zap, Shield, ChevronDown } from 'lucide-react'
import { motion } from 'framer-motion'
import { api } from '../../lib/api'

export function StrategyIntelligence() {
  const [performance, setPerformance] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getPortfolioPerformance().then(setPerformance).finally(() => setLoading(false))
  }, [])

  if (loading || !performance) return null

  return (
    <div className="w-full max-w-7xl mx-auto px-4 py-12 space-y-12">
      
      {/* Overview Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-8 border-b border-white/5 pb-12">
        <div>
          <div className="flex items-center gap-3 mb-4">
             <div className="p-2 bg-brand-accent/10 rounded-xl">
               <TrendingUp className="w-5 h-5 text-brand-accent" />
             </div>
             <span className="text-[10px] font-black uppercase tracking-[0.3em] text-brand-text-dim">Quantitative Intelligence</span>
          </div>
          <h2 className="text-5xl font-black text-white tracking-tighter italic uppercase">Strategy Performance</h2>
          <p className="text-sm text-brand-text-dim mt-4 max-w-xl font-medium leading-relaxed">
            Real-time attribution and risk calibration for the <span className="text-white">Sovereign High-Conviction</span> universe. Derived from multi-factor institutional scoring models.
          </p>
        </div>

        <div className="flex gap-4">
          <div className="bg-brand-card/40 border border-white/5 p-6 rounded-2xl min-w-[160px]">
            <div className="text-[9px] text-brand-text-dim font-black uppercase tracking-widest mb-2">CAGR (PROJECTED)</div>
            <div className="text-3xl font-mono font-black text-brand-accent">+{performance.stats.cagr}%</div>
          </div>
          <div className="bg-brand-card/40 border border-white/5 p-6 rounded-2xl min-w-[160px]">
            <div className="text-[9px] text-brand-text-dim font-black uppercase tracking-widest mb-2">PROFIT FACTOR</div>
            <div className="text-3xl font-mono font-black text-white">{performance.stats.profit_factor}</div>
          </div>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        
        {/* Core Metrics */}
        <div className="col-span-1 md:col-span-2 bg-brand-card/20 border border-white/5 rounded-3xl p-8 relative overflow-hidden group">
          <div className="absolute top-0 right-0 w-64 h-64 bg-brand-accent/5 blur-[100px] pointer-events-none" />
          
          <div className="flex items-center justify-between mb-8">
            <h3 className="text-xs font-black uppercase tracking-[0.2em] text-white flex items-center gap-3">
              <BarChart3 className="w-4 h-4 text-brand-accent" />
              Intelligence attribution
            </h3>
            <button className="text-[10px] font-bold text-brand-text-dim hover:text-white transition-colors flex items-center gap-2">
              LAST 30 DAYS <ChevronDown className="w-3 h-3" />
            </button>
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-8">
             <div className="space-y-1">
               <div className="text-[9px] text-brand-text-dim font-black uppercase tracking-widest">Win Rate</div>
               <div className="text-2xl font-mono font-black text-white">{performance.stats.win_rate}%</div>
               <div className="w-full h-1 bg-white/5 rounded-full mt-2">
                 <motion.div initial={{width: 0}} animate={{width: '62%'}} className="h-full bg-brand-accent" />
               </div>
             </div>
             <div className="space-y-1">
               <div className="text-[9px] text-brand-text-dim font-black uppercase tracking-widest">Sharpe</div>
               <div className="text-2xl font-mono font-black text-white">{performance.stats.sharpe}</div>
               <div className="w-full h-1 bg-white/5 rounded-full mt-2">
                 <motion.div initial={{width: 0}} animate={{width: '75%'}} className="h-full bg-brand-gold" />
               </div>
             </div>
             <div className="space-y-1">
               <div className="text-[9px] text-brand-text-dim font-black uppercase tracking-widest">Max DD</div>
               <div className="text-2xl font-mono font-black text-brand-rose">{performance.stats.max_drawdown}%</div>
               <div className="w-full h-1 bg-white/5 rounded-full mt-2">
                 <motion.div initial={{width: 0}} animate={{width: '15%'}} className="h-full bg-brand-rose" />
               </div>
             </div>
             <div className="space-y-1">
               <div className="text-[9px] text-brand-text-dim font-black uppercase tracking-widest">Alpha</div>
               <div className="text-2xl font-mono font-black text-green-400">+4.2%</div>
               <div className="w-full h-1 bg-white/5 rounded-full mt-2">
                 <motion.div initial={{width: 0}} animate={{width: '80%'}} className="h-full bg-green-500" />
               </div>
             </div>
          </div>
        </div>

        {/* Confidence Radar (Mock) */}
        <div className="bg-brand-card/40 border border-white/5 rounded-3xl p-8">
          <h3 className="text-xs font-black uppercase tracking-[0.2em] text-white flex items-center gap-3 mb-8">
            <Shield className="w-4 h-4 text-brand-accent" />
            Confidence Radar
          </h3>
          <div className="space-y-6">
            {[
              { label: 'Trend Strength', value: 85, color: 'text-brand-accent' },
              { label: 'Fundamental Base', value: 92, color: 'text-green-400' },
              { label: 'Volatility Risk', value: 34, color: 'text-brand-rose' },
              { label: 'Liquidity Depth', value: 78, color: 'text-brand-gold' },
            ].map(item => (
              <div key={item.label} className="space-y-2">
                <div className="flex justify-between text-[10px] font-bold uppercase tracking-widest">
                  <span className="text-brand-text-dim">{item.label}</span>
                  <span className={item.color}>{item.value}%</span>
                </div>
                <div className="h-1 w-full bg-white/5 rounded-full overflow-hidden">
                  <motion.div 
                    initial={{ width: 0 }}
                    animate={{ width: `${item.value}%` }}
                    className={`h-full ${item.color.replace('text', 'bg')}`}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

      </div>

      {/* System Alerts Strip */}
      <div className="bg-brand-accent/5 border border-brand-accent/20 rounded-2xl p-6 flex flex-col md:flex-row items-center gap-6">
        <div className="flex items-center gap-3 shrink-0">
          <div className="p-2 bg-brand-accent/20 rounded-lg">
            <Zap className="w-5 h-5 text-brand-accent animate-pulse" />
          </div>
          <div>
            <div className="text-xs font-black text-white uppercase tracking-tighter italic">Live Intelligence Feed</div>
            <div className="text-[9px] text-brand-accent font-bold uppercase tracking-widest">Active Alerts: 03</div>
          </div>
        </div>
        <div className="h-px md:h-8 w-full md:w-px bg-brand-accent/20" />
        <div className="flex-1 overflow-hidden">
          <div className="flex gap-12 animate-[scroll_30s_linear_infinite] whitespace-nowrap">
            {[
              'NSE:RELIANCE - VOLUMETRIC BREAKOUT DETECTED (+2.4x)',
              'NSE:TCS - QUARTERLY ALPHA MOMENTUM ACCELERATING',
              'MARKET REGIME: RISK-ON (VIX 12.4) - EXPANDING SWING POSITIONS',
              'NSE:HDFCBANK - INSTITUTIONAL ACCUMULATION ZONE REACHED',
            ].map((alert, i) => (
              <span key={i} className="text-[10px] font-mono text-brand-text/80 font-medium">
                <span className="text-brand-accent mr-2">{" >>> "}</span> {alert}
              </span>
            ))}
          </div>
        </div>
      </div>

    </div>
  )
}
