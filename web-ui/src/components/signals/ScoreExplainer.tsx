import { useEffect, useState } from 'react'
import { BrainCircuit, TrendingUp, TrendingDown, ShieldAlert, CheckCircle, XCircle, Minus } from 'lucide-react'
import { api } from '../../lib/api'
import type { ScoreExplanationResponse } from '../../lib/contracts'

interface ScoreExplainerProps {
  symbol: string
}

export function ScoreExplainer({ symbol }: ScoreExplainerProps) {
  const [data, setData] = useState<ScoreExplanationResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.getScoreExplanation(symbol)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [symbol])

  if (loading) {
    return (
      <div className="animate-pulse space-y-4">
        <div className="h-5 w-32 bg-white/10 rounded" />
        <div className="h-20 w-full bg-white/5 rounded" />
      </div>
    )
  }

  if (!data || 'error' in data) return null

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 mb-4 border-b border-white/10 pb-4">
        <BrainCircuit className="text-brand-accent" size={20} />
        <h2 className="font-mono text-lg font-bold uppercase tracking-widest text-brand-text">
          Why This Score?
        </h2>
        {data.score_delta && (
          <span className={`ml-auto inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono font-bold ${
            data.score_delta.direction === 'UP' ? 'bg-brand-accent/10 text-brand-accent' :
            data.score_delta.direction === 'DOWN' ? 'bg-brand-rose/10 text-brand-rose' :
            'bg-white/5 text-brand-text-dim'
          }`}>
            {data.score_delta.direction === 'UP' ? <TrendingUp size={10} /> :
             data.score_delta.direction === 'DOWN' ? <TrendingDown size={10} /> :
             <Minus size={10} />}
            {data.score_delta.delta > 0 ? '+' : ''}{data.score_delta.delta}
          </span>
        )}
      </div>

      {/* Positive Drivers */}
      {data.top_positive_drivers.length > 0 && (
        <div>
          <h4 className="font-mono text-[10px] font-bold uppercase tracking-widest text-brand-accent mb-3">
            Positive Drivers
          </h4>
          <div className="space-y-2">
            {data.top_positive_drivers.map((d, i) => (
              <div key={i} className="flex items-center gap-3">
                <div className={`h-2 rounded-full bg-brand-accent transition-all duration-700`}
                  style={{ width: d.impact === 'high' ? '100%' : d.impact === 'medium' ? '66%' : '33%', maxWidth: '120px', minWidth: '32px' }}
                />
                <span className="font-mono text-xs text-brand-text flex-1 truncate">{d.factor}</span>
                <span className="font-mono text-xs text-brand-text-dim">{d.value}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Penalties */}
      {data.top_penalties.length > 0 && (
        <div>
          <h4 className="font-mono text-[10px] font-bold uppercase tracking-widest text-brand-rose mb-3">
            Penalties
          </h4>
          <div className="space-y-2">
            {data.top_penalties.map((p, i) => (
              <div key={i} className="flex items-center gap-3">
                <div className="h-2 rounded-full bg-brand-rose transition-all duration-700"
                  style={{ width: p.impact === 'high' ? '100%' : p.impact === 'medium' ? '66%' : '33%', maxWidth: '120px', minWidth: '32px' }}
                />
                <span className="font-mono text-xs text-brand-text flex-1 truncate">{p.factor}</span>
                <span className="font-mono text-xs text-brand-text-dim">{p.value}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Active Ceilings */}
      {data.active_ceilings.length > 0 && (
        <div>
          <h4 className="font-mono text-[10px] font-bold uppercase tracking-widest text-brand-gold mb-3">
            <ShieldAlert className="inline h-3 w-3 mr-1" />
            Active Score Ceilings
          </h4>
          <div className="space-y-1.5">
            {data.active_ceilings.map((c, i) => (
              <div key={i} className="flex items-center justify-between p-2 rounded bg-brand-gold/5 border border-brand-gold/10">
                <span className="font-mono text-xs text-brand-text">{c.name}</span>
                <span className="font-mono text-xs font-bold text-brand-gold">Cap: {c.cap}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Checklist */}
      <div>
        <h4 className="font-mono text-[10px] font-bold uppercase tracking-widest text-brand-text-dim mb-3">
          Quality Checklist ({data.checklist_status.passed}/{data.checklist_status.total})
          <span className={`ml-2 px-1.5 py-0.5 rounded text-[9px] ${
            data.checklist_status.grade === 'A' ? 'bg-brand-accent/10 text-brand-accent' :
            data.checklist_status.grade === 'B' ? 'bg-brand-gold/10 text-brand-gold' :
            'bg-brand-rose/10 text-brand-rose'
          }`}>
            Grade {data.checklist_status.grade}
          </span>
        </h4>
        <div className="grid grid-cols-2 gap-1.5">
          {Object.entries(data.checklist_status.items).map(([name, passed]) => (
            <div key={name} className="flex items-center gap-1.5 text-xs font-mono">
              {passed ? (
                <CheckCircle className="h-3 w-3 text-brand-accent flex-shrink-0" />
              ) : (
                <XCircle className="h-3 w-3 text-brand-rose flex-shrink-0" />
              )}
              <span className={passed ? 'text-brand-text' : 'text-brand-text-dim'}>{name}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Missing Factors */}
      {data.missing_factors.length > 0 && (
        <div className="p-3 rounded bg-white/5 border border-white/10">
          <h4 className="font-mono text-[10px] font-bold uppercase tracking-widest text-brand-text-dim mb-2">
            Missing Data ({data.missing_factors.length} factors)
          </h4>
          <p className="font-mono text-xs text-brand-text-dim">
            {data.missing_factors.join(', ')}
          </p>
        </div>
      )}

      {/* Score Change */}
      {data.score_delta && (
        <div className={`p-3 rounded border ${
          data.score_delta.direction === 'UP' ? 'bg-brand-accent/5 border-brand-accent/20' :
          data.score_delta.direction === 'DOWN' ? 'bg-brand-rose/5 border-brand-rose/20' :
          'bg-white/5 border-white/10'
        }`}>
          <h4 className="font-mono text-[10px] font-bold uppercase tracking-widest text-brand-text-dim mb-1">
            Score Changed Because…
          </h4>
          <p className="font-mono text-xs text-brand-text">{data.score_delta.reason}</p>
          <p className="font-mono text-[10px] text-brand-text-dim mt-1">
            Previous: {data.score_delta.previous_score} on {data.score_delta.previous_date}
          </p>
        </div>
      )}
    </div>
  )
}
