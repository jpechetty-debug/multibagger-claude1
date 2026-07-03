import React, { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { X, Shield, Target, AlertTriangle, ArrowRight, Wallet, Activity, Loader2 } from 'lucide-react'
import type { SwingTrade, PortfolioState } from '../../lib/contracts'
import { api } from '../../lib/api'

interface TradeExecutionModalProps {
  trade: SwingTrade
  onClose: () => void
  onSuccess: () => void
}

export function TradeExecutionModal({ trade, onClose, onSuccess }: TradeExecutionModalProps) {
  const [portfolio, setPortfolio] = useState<PortfolioState | null>(null)
  const [loading, setLoading] = useState(true)
  const [executing, setExecuting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Risk Sizing State
  const [riskPct, setRiskPct] = useState(1.0) // 1% default
  const [quantity, setQuantity] = useState(0)
  const [totalCost, setTotalCost] = useState(0)
  const [riskAmount, setRiskAmount] = useState(0)

  useEffect(() => {
    api.getPortfolioState()
      .then(p => {
        setPortfolio(p)
        setRiskPct(p.risk_per_trade_pct)
        setLoading(false)
      })
      .catch(() => {
        setError("Failed to load portfolio state")
        setLoading(false)
      })
  }, [])

  useEffect(() => {
    if (!portfolio || !trade) return

    const capital = portfolio.available_capital
    const riskVal = capital * (riskPct / 100)
    setRiskAmount(riskVal)

    const riskPerShare = trade.ltp - trade.sl
    if (riskPerShare > 0) {
      const qty = Math.floor(riskVal / riskPerShare)
      setQuantity(qty)
      setTotalCost(qty * trade.ltp)
    }
  }, [riskPct, portfolio, trade])

  const handleExecute = async () => {
    setExecuting(true)
    setError(null)
    try {
      // In a real app, we'd call api.placeOrder
      // For now, let's simulate success
      await new Promise(r => setTimeout(r, 1500))
      onSuccess()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Execution failed")
    } finally {
      setExecuting(false)
    }
  }

  if (loading) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <motion.div 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="absolute inset-0 bg-brand-bg/80 backdrop-blur-md" 
      />
      
      <motion.div
        initial={{ opacity: 0, scale: 0.9, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.9, y: 20 }}
        className="relative w-full max-w-xl bg-brand-card/95 border border-white/10 rounded-3xl shadow-[0_50px_100px_rgba(0,0,0,0.5)] overflow-hidden"
      >
        {/* Header */}
        <div className="p-6 border-b border-white/5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-brand-accent/10 rounded-xl">
              <Shield className="w-5 h-5 text-brand-accent" />
            </div>
            <div>
              <h2 className="text-lg font-black uppercase tracking-tighter text-white italic">
                Execution Blueprint: {trade.symbol}
              </h2>
              <p className="text-[10px] text-brand-text-dim uppercase tracking-widest font-bold">
                Dynamic Risk Calibration Engine
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 text-brand-text-dim hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-8 space-y-8">
          {/* Market Context */}
          <div className="grid grid-cols-2 gap-8">
            <div>
              <label className="text-[9px] text-brand-text-dim uppercase font-black tracking-widest mb-2 block">Entry Execution</label>
              <div className="text-2xl font-mono font-black text-white italic">₹{trade.ltp.toLocaleString('en-IN')}</div>
            </div>
            <div className="text-right">
              <label className="text-[9px] text-brand-rose uppercase font-black tracking-widest mb-2 block">Risk Floor (SL)</label>
              <div className="text-2xl font-mono font-black text-brand-rose/80 italic">₹{trade.sl.toLocaleString('en-IN')}</div>
            </div>
          </div>

          {/* Risk Control */}
          <div className="bg-white/5 border border-white/5 rounded-2xl p-6 space-y-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Wallet className="w-4 h-4 text-brand-accent" />
              <span className="text-[10px] font-black uppercase tracking-widest text-brand-text-dim">Portfolio Risk Parameter</span>
              </div>
              <span className="text-sm font-mono font-black text-brand-accent">
                {riskPct}% / â‚¹{riskAmount.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
              </span>
            </div>
            
            <input 
              type="range"
              min="0.25"
              max="5.0"
              step="0.25"
              value={riskPct}
              onChange={(e) => setRiskPct(parseFloat(e.target.value))}
              className="w-full h-1.5 bg-white/10 rounded-full appearance-none cursor-pointer accent-brand-accent"
            />
            
            <div className="flex justify-between text-[10px] font-bold text-brand-text-dim/60 uppercase">
              <span>Conservative (0.25%)</span>
              <span>Aggressive (5%)</span>
            </div>
          </div>

          {/* Sizing Results */}
          <div className="grid grid-cols-2 gap-4">
            <div className="p-5 bg-brand-accent/[0.03] border border-brand-accent/10 rounded-2xl">
              <div className="text-[9px] text-brand-accent font-black uppercase tracking-widest mb-2">Calculated Quantity</div>
              <div className="text-3xl font-mono font-black text-white">{quantity} <span className="text-[10px] text-brand-text-dim font-normal">SHARES</span></div>
            </div>
            <div className="p-5 bg-white/[0.03] border border-white/10 rounded-2xl">
              <div className="text-[9px] text-brand-text-dim font-black uppercase tracking-widest mb-2">Total Exposure</div>
              <div className="text-xl font-mono font-black text-white">₹{totalCost.toLocaleString('en-IN')}</div>
            </div>
          </div>

          {/* Warning */}
          {totalCost > (portfolio?.available_capital || 0) && (
            <div className="flex items-start gap-3 p-4 bg-brand-rose/10 border border-brand-rose/20 rounded-xl text-[10px] text-brand-rose font-bold uppercase leading-relaxed">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>Insufficient Capital for this Risk Profile. Adjust Risk Parameter or Deploy Available Liquidity.</span>
            </div>
          )}

          {error && (
            <div className="flex items-start gap-3 p-4 bg-brand-rose/10 border border-brand-rose/20 rounded-xl text-[10px] text-brand-rose font-bold uppercase leading-relaxed">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Action */}
          <button
            disabled={executing || totalCost > (portfolio?.available_capital || 0)}
            onClick={handleExecute}
            className="w-full group relative overflow-hidden bg-brand-accent py-5 rounded-2xl flex items-center justify-center gap-3 transition-all active:scale-95 disabled:opacity-50 disabled:grayscale"
          >
            <div className="absolute inset-0 bg-white/10 translate-y-full group-hover:translate-y-0 transition-transform duration-500" />
            
            {executing ? (
              <Loader2 className="w-5 h-5 text-brand-bg animate-spin" />
            ) : (
              <>
                <span className="text-[11px] font-black uppercase tracking-[0.3em] text-brand-bg">Execute Paper Entry</span>
                <ArrowRight className="w-4 h-4 text-brand-bg" />
              </>
            )}
          </button>
        </div>

        {/* Footer */}
        <div className="p-6 bg-white/[0.02] border-t border-white/5 flex items-center justify-between text-[9px] font-bold text-brand-text-dim uppercase tracking-widest">
          <div className="flex items-center gap-2">
            <Target className="w-3.5 h-3.5" />
            Target: ₹{trade.target.toLocaleString('en-IN')}
          </div>
          <div className="flex items-center gap-2">
            <Activity className="w-3.5 h-3.5" />
            R:R {trade.reward_risk_ratio}:1
          </div>
        </div>
      </motion.div>
    </div>
  )
}
