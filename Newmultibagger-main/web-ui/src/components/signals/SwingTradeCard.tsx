import React, { useState } from 'react'
import { AlertTriangle, Crosshair, Activity, Clock, Star, ArrowRight } from 'lucide-react'
import type { SwingTrade } from '../../lib/contracts'
import { motion, AnimatePresence } from 'framer-motion'
import { TradeExecutionModal } from '../trading/TradeExecutionModal'

interface SwingTradeCardProps {
  trade: SwingTrade
}

export function SwingTradeCard({ trade }: SwingTradeCardProps) {
  const [showModal, setShowModal] = useState(false)
  const isPositiveChange = trade.ltp_change_pct > 0
  const isStaleSnapshot = (trade.snapshot_age_days ?? 0) > 2
  const canExecute = !isStaleSnapshot && trade.status !== 'STALE'
  
  return (
    <motion.div 
      whileHover={{ y: -4 }}
      className="relative group overflow-hidden bg-brand-card/40 border border-white/5 hover:border-brand-accent/40 transition-all duration-500 rounded-2xl w-full"
    >
      
      {/* Background Accent Gradient */}
      <div className="absolute top-0 right-0 w-64 h-64 bg-brand-accent/5 blur-[80px] group-hover:bg-brand-accent/10 transition-colors duration-500 pointer-events-none" />
      
      {/* Header Area */}
      <div className="p-5 border-b border-white/5 flex flex-col md:flex-row justify-between items-start md:items-center gap-4 relative z-10">
        <div className="flex items-center gap-4">
          {/* Score Gauge */}
          <div className="relative w-12 h-12 flex items-center justify-center shrink-0">
            <svg className="w-12 h-12 -rotate-90">
              <circle cx="24" cy="24" r="20" fill="transparent" stroke="currentColor" strokeWidth="3" className="text-white/5" />
              <motion.circle 
                cx="24" 
                cy="24" 
                r="20" 
                fill="transparent" 
                stroke="currentColor" 
                strokeWidth="3" 
                strokeDasharray="125.6" 
                initial={{ strokeDashoffset: 125.6 }}
                animate={{ strokeDashoffset: 125.6 - (125.6 * trade.score) / 100 }}
                transition={{ duration: 1.5, ease: "easeOut", delay: 0.2 }}
                className="text-brand-accent"
              />
            </svg>
            <span className="absolute text-[10px] font-black text-white">{Math.round(trade.score)}</span>
          </div>

          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className={`px-2 py-0.5 text-[9px] font-black uppercase tracking-widest border ${
                trade.status === 'ACTIVE' ? 'bg-brand-accent/10 text-brand-accent border-brand-accent/20' :
                trade.status === 'EXTENDED' ? 'bg-brand-rose/10 text-brand-rose border-brand-rose/20' :
                trade.status === 'STALE' ? 'bg-orange-500/10 text-orange-400 border-orange-500/20' :
                'bg-blue-500/10 text-blue-400 border-blue-500/20'
              }`}>
                {trade.status}
              </span>
              <span className="px-2 py-0.5 bg-white/5 text-brand-text-dim text-[9px] font-bold uppercase tracking-widest border border-white/10">
                {trade.type}
              </span>
              <span className={`px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest border ${
                trade.risk === 'HIGH' ? 'text-brand-rose border-brand-rose/20' :
                trade.risk === 'MEDIUM' ? 'text-orange-400 border-orange-500/20' :
                'text-green-400 border-green-500/20'
              }`}>
                {trade.risk} RISK
              </span>
              {trade.rating && (
                <span className="px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest border border-white/10 text-brand-text-dim">
                  {trade.rating}
                </span>
              )}
              {typeof trade.data_quality === 'number' && (
                <span className="px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest border border-brand-accent/20 text-brand-accent">
                  DQ {Math.round(trade.data_quality)}
                </span>
              )}
              {isStaleSnapshot && (
                <span className="px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest border border-orange-500/20 text-orange-400">
                  STALE {trade.snapshot_age_days}D
                </span>
              )}
            </div>
            <h2 className="text-2xl font-black tracking-tighter text-white uppercase italic">
              {trade.symbol.replace('NSE:', '').replace('-EQ', '')}
              <span className="ml-2 text-[9px] font-mono text-brand-text-dim/40 font-normal tracking-widest uppercase not-italic">
                {trade.symbol}
              </span>
            </h2>
          </div>
        </div>
        
        <div className="flex items-center gap-4">
          <div className="text-right hidden sm:block">
            <div className="text-[9px] text-brand-text-dim font-bold uppercase tracking-widest mb-0.5">Report Date</div>
            <div className="text-[10px] font-mono text-white/60 flex items-center gap-1.5 uppercase">
              <Clock className="w-3 h-3" />
              {trade.date}
            </div>
          </div>
          <button className="p-2.5 bg-white/5 border border-white/10 text-brand-text-dim hover:text-brand-accent hover:border-brand-accent/50 transition-all active:scale-90 rounded-xl">
            <Star className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Main Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-12 relative z-10">
        
        {/* Left: Price & Analysis (7 Cols) */}
        <div className="col-span-1 md:col-span-7 p-6 border-r border-white/5 flex flex-col justify-between gap-6">
          
          <div className="flex flex-wrap items-end gap-x-8 gap-y-4">
            <div>
              <div className="text-[9px] text-brand-text-dim font-black uppercase tracking-[0.2em] mb-2">Market Price</div>
              <div className="flex items-baseline gap-2">
              <span className="text-4xl font-mono font-bold text-white tracking-tighter leading-none">
                  ₹{trade.ltp.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </span>
                <span className={`text-xs font-mono font-bold px-1.5 py-0.5 rounded-md ${isPositiveChange ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}
                  title="1-month return, not daily change"
                >
                  {isPositiveChange ? '▲' : '▼'}{Math.abs(trade.ret_1m_pct ?? trade.ltp_change_pct)}%
                  <span className="text-[8px] ml-0.5 opacity-60">1M</span>
                </span>
              </div>
            </div>
            
            <div className="w-[1px] h-10 bg-white/10 hidden lg:block" />
            
            <div>
              <div className="text-[9px] text-brand-text-dim font-black uppercase tracking-[0.2em] mb-2">Ideal Accumulation</div>
              <div className="text-lg font-mono font-bold text-white/90 italic">
                {trade.entry_range[0].toLocaleString('en-IN')} <span className="text-brand-text-dim/30 mx-1">—</span> {trade.entry_range[1].toLocaleString('en-IN')}
              </div>
            </div>
          </div>
          
          <div className="bg-brand-bg/40 p-4 border-l-2 border-brand-accent relative overflow-hidden group/analysis">
            <div className="absolute right-0 top-0 p-1 opacity-10 group-hover/analysis:opacity-30 transition-opacity">
              <Activity className="w-8 h-8 text-brand-accent" />
            </div>
            <p className="text-xs text-brand-text/80 leading-relaxed font-medium">
              {trade.analysis}
            </p>
          </div>
          
        </div>

        {/* Right: Targets & R:R (5 Cols) */}
        <div className="col-span-1 md:col-span-5 flex flex-col">
          
          {/* Target Zone */}
          <div className="flex-1 p-6 bg-brand-accent/[0.03] border-b border-white/5 relative overflow-hidden">
            <div className="text-[9px] text-brand-accent font-black uppercase tracking-[0.2em] mb-3 flex items-center gap-2">
              <Crosshair className="w-3 h-3" /> ATR Target
            </div>
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="text-3xl font-mono font-black text-white tracking-tighter">
                  ₹{trade.target.toLocaleString('en-IN')}
                </div>
                <div className="text-[10px] text-brand-accent font-bold mt-1">
                  UPSIDE: +{trade.target_pct}%
                </div>
              </div>
              <div className="bg-brand-accent/10 border border-brand-accent/20 px-3 py-2 text-center rounded-lg">
                <div className="text-[8px] text-brand-accent font-black uppercase tracking-tighter mb-0.5">Reward/Risk</div>
                <div className="text-sm font-black text-white">{trade.reward_risk_ratio}:1</div>
              </div>
            </div>
            
            <div className="w-full h-1.5 bg-white/5 rounded-full overflow-hidden">
              <motion.div 
                initial={{ width: 0 }}
                animate={{ width: `${Math.min((trade.ltp / trade.target) * 100, 100)}%` }}
                className="h-full bg-brand-accent opacity-50"
              />
            </div>
          </div>
          
          {/* Stop Loss Zone */}
          <div className="p-6 bg-brand-rose/[0.03] relative overflow-hidden group/sl flex items-center justify-between">
            <div>
              <div className="text-[9px] text-brand-rose font-black uppercase tracking-[0.2em] mb-2 flex items-center gap-2">
                <AlertTriangle className="w-3 h-3" /> Risk Limit
              </div>
              <div className="text-xl font-mono font-bold text-white/80 tracking-tight">
                ₹{trade.sl.toLocaleString('en-IN')}
              </div>
            </div>
            
            <button 
              onClick={() => {
                if (canExecute) setShowModal(true)
              }}
              disabled={!canExecute}
              title={canExecute ? 'Execute paper trade' : 'Refresh market data before execution'}
              className={`border px-4 py-2 text-[10px] font-black uppercase tracking-widest transition-all rounded-lg flex items-center gap-2 ${
                canExecute
                  ? 'bg-brand-accent/10 hover:bg-brand-accent text-brand-accent hover:text-brand-bg border-brand-accent/30'
                  : 'bg-white/5 text-brand-text-dim border-white/10 cursor-not-allowed opacity-60'
              }`}
            >
              {canExecute ? 'Execute' : 'Refresh'} <ArrowRight className="w-3 h-3" />
            </button>
          </div>
          
        </div>
      </div>

      <AnimatePresence>
        {showModal && (
          <TradeExecutionModal 
            trade={trade} 
            onClose={() => setShowModal(false)}
            onSuccess={() => {
              // Notification would go here
            }}
          />
        )}
      </AnimatePresence>
    </motion.div>
  )
}
