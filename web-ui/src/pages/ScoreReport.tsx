import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, BarChart3, AlertTriangle, CheckCircle } from 'lucide-react'
import { motion } from 'framer-motion'
import { api } from '../lib/api'
import type { ScoreDistributionResponse, CalibrationReportResponse } from '../lib/contracts'
import { ProviderHealthPanel } from '../components/metrics/ProviderHealthPanel'

export function ScoreReport() {
  const [dist, setDist] = useState<ScoreDistributionResponse | null>(null)
  const [calibration, setCalibration] = useState<CalibrationReportResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      api.getScoreDistribution(),
      api.getCalibrationReport(),
    ])
      .then(([d, c]) => {
        setDist(d)
        setCalibration(c)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-brand-bg text-brand-text">
        <div className="animate-pulse font-mono tracking-widest text-brand-accent uppercase font-bold">
          [ COMPUTING SCORE DISTRIBUTION ]
        </div>
      </div>
    )
  }

  const decileEntries = dist ? Object.entries(dist.deciles) : []
  const maxDecile = Math.max(...decileEntries.map(([, v]) => v), 1)

  return (
    <div className="min-h-screen bg-brand-bg text-brand-text p-4 md:p-8 pb-32">
      <Link
        to="/"
        className="inline-flex items-center gap-2 mb-8 font-mono text-sm tracking-widest text-brand-text-dim hover:text-brand-accent transition-colors uppercase"
      >
        <ArrowLeft size={16} />
        Dashboard
      </Link>

      <div className="brutalist-card p-6 md:p-8 mb-8 border-l-4 border-l-brand-accent">
        <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-brand-text-dim font-bold">
          Score Intelligence
        </p>
        <h2 className="font-display text-3xl font-black tracking-tight mt-1">
          Distribution & Calibration Report
        </h2>
        <p className="text-sm text-brand-text-dim mt-2">
          Analyze scoring engine health, identify clustering, and validate differentiation.
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-8">
        {/* Left: Distribution + Stats */}
        <div className="xl:col-span-2 space-y-8">

          {/* Decile Histogram */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="brutalist-card p-6"
          >
            <div className="flex items-center gap-2 mb-6">
              <BarChart3 className="text-brand-accent" size={20} />
              <h3 className="font-mono text-lg font-bold uppercase tracking-widest">
                Score Distribution
              </h3>
              {dist && (
                <span className="ml-auto font-mono text-xs text-brand-text-dim">
                  {dist.total} stocks
                </span>
              )}
            </div>

            <div className="flex items-end gap-2 h-48">
              {decileEntries.map(([label, count]) => {
                const height = (count / maxDecile) * 100
                const isGraveyard = label === '50-60' || label === '60-70'
                return (
                  <div key={label} className="flex-1 flex flex-col items-center gap-1">
                    <span className="font-mono text-[10px] font-bold text-brand-text">{count}</span>
                    <div
                      className={`w-full rounded-t transition-all duration-700 ${
                        isGraveyard ? 'bg-brand-gold' :
                        label === '90-100' ? 'bg-brand-accent' :
                        'bg-brand-accent/40'
                      }`}
                      style={{ height: `${Math.max(height, 2)}%` }}
                    />
                    <span className="font-mono text-[8px] text-brand-text-dim">{label}</span>
                  </div>
                )
              })}
            </div>

            {dist && dist.graveyard_pct > 10 && (
              <div className="mt-4 p-3 rounded bg-brand-gold/5 border border-brand-gold/20 flex items-start gap-2">
                <AlertTriangle className="h-4 w-4 text-brand-gold flex-shrink-0 mt-0.5" />
                <div>
                  <p className="font-mono text-xs font-bold text-brand-gold">Score Graveyard Detected</p>
                  <p className="font-mono text-[10px] text-brand-text-dim mt-1">
                    {dist.graveyard_pct}% of stocks ({dist.graveyard_count}/{dist.total}) clustered at 59-61. Ceiling splines are converging.
                  </p>
                </div>
              </div>
            )}
          </motion.div>

          {/* Summary Stats */}
          {dist?.stats && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="brutalist-card p-6"
            >
              <h3 className="font-mono text-xs font-bold uppercase tracking-widest text-brand-text-dim mb-4">
                Statistical Summary
              </h3>
              <div className="grid grid-cols-3 md:grid-cols-5 gap-4">
                {[
                  ['Mean', dist.stats.mean],
                  ['Median', dist.stats.median],
                  ['Std Dev', dist.stats.std],
                  ['P5', dist.stats.p5],
                  ['P95', dist.stats.p95],
                  ['Min', dist.stats.min],
                  ['Max', dist.stats.max],
                  ['P25', dist.stats.p25],
                  ['P75', dist.stats.p75],
                  ['Top 5%', dist.top5_threshold],
                ].map(([label, value]) => (
                  <div key={String(label)} className="p-3 bg-black/40 border border-white/5 rounded">
                    <span className="font-mono text-[9px] uppercase text-brand-text-dim">{label}</span>
                    <div className="mt-1 font-display text-lg font-bold text-brand-text">
                      {typeof value === 'number' ? value.toFixed(1) : value}
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          )}

          {/* Sector Breakdown */}
          {dist?.sector_breakdown && Object.keys(dist.sector_breakdown).length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="brutalist-card p-6"
            >
              <h3 className="font-mono text-xs font-bold uppercase tracking-widest text-brand-text-dim mb-4">
                Sector Score Ranges
              </h3>
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {Object.entries(dist.sector_breakdown)
                  .sort(([, a], [, b]) => b.median - a.median)
                  .map(([sector, stats]) => (
                    <div key={sector} className="flex items-center gap-3 p-2 rounded bg-white/[0.02] hover:bg-white/[0.04] transition-colors">
                      <span className="font-mono text-xs text-brand-text w-40 truncate">{sector}</span>
                      <div className="flex-1 h-1.5 bg-white/5 rounded-full overflow-hidden relative">
                        <div
                          className="absolute h-full bg-brand-accent/30 rounded-full"
                          style={{ left: `${stats.min}%`, width: `${stats.max - stats.min}%` }}
                        />
                        <div
                          className="absolute h-full w-1 bg-brand-accent rounded-full"
                          style={{ left: `${stats.median}%` }}
                        />
                      </div>
                      <span className="font-mono text-[10px] text-brand-text-dim w-12 text-right">
                        μ{stats.median.toFixed(0)}
                      </span>
                      <span className="font-mono text-[10px] text-brand-text-dim w-8 text-right">
                        n={stats.count}
                      </span>
                    </div>
                  ))}
              </div>
            </motion.div>
          )}
        </div>

        {/* Right: Calibration Health + Provider Health */}
        <div className="xl:col-span-1 space-y-6">
          {/* Calibration Health */}
          {calibration && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15 }}
              className={`brutalist-card p-5 border-l-4 ${
                calibration.health === 'GOOD' ? 'border-l-brand-accent' :
                calibration.health === 'NEEDS_ATTENTION' ? 'border-l-brand-gold' :
                'border-l-brand-rose'
              }`}
            >
              <div className="flex items-center gap-2 mb-4">
                {calibration.health === 'GOOD' ? (
                  <CheckCircle className="h-5 w-5 text-brand-accent" />
                ) : (
                  <AlertTriangle className={`h-5 w-5 ${calibration.health === 'POOR' ? 'text-brand-rose' : 'text-brand-gold'}`} />
                )}
                <h3 className="font-mono text-xs font-bold uppercase tracking-widest text-brand-text-dim">
                  Calibration Health
                </h3>
              </div>

              <div className={`font-display text-2xl font-black ${
                calibration.health === 'GOOD' ? 'text-brand-accent' :
                calibration.health === 'NEEDS_ATTENTION' ? 'text-brand-gold' :
                'text-brand-rose'
              }`}>
                {calibration.health.replace('_', ' ')}
              </div>

              <p className="font-mono text-[10px] text-brand-text-dim mt-2">
                Effective range: {calibration.effective_range}
              </p>
              <p className="font-mono text-[10px] text-brand-text-dim">
                Top 5% rarity: {calibration.top5_rarity_pct}%
              </p>

              {calibration.calibration_issues.length > 0 && (
                <div className="mt-4 space-y-2">
                  {calibration.calibration_issues.map((issue, i) => (
                    <div
                      key={i}
                      className={`p-2.5 rounded border ${
                        issue.severity === 'CRITICAL' ? 'bg-brand-rose/5 border-brand-rose/20' : 'bg-brand-gold/5 border-brand-gold/10'
                      }`}
                    >
                      <p className={`font-mono text-xs font-bold ${
                        issue.severity === 'CRITICAL' ? 'text-brand-rose' : 'text-brand-gold'
                      }`}>
                        {issue.issue}
                      </p>
                      <p className="font-mono text-[10px] text-brand-text-dim mt-1">{issue.fix}</p>
                    </div>
                  ))}
                </div>
              )}
            </motion.div>
          )}

          {/* Provider Health */}
          <ProviderHealthPanel />
        </div>
      </div>
    </div>
  )
}
