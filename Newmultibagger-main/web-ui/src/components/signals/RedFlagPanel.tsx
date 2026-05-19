import { AlertTriangle, ShieldAlert, TrendingDown, Users } from 'lucide-react'
import type { BackendStockRecord } from '../../lib/contracts'

interface RedFlagPanelProps {
  stock: BackendStockRecord
}

interface RedFlag {
  severity: 'CRITICAL' | 'WARNING' | 'INFO'
  label: string
  value: string
  icon: typeof AlertTriangle
}

export function RedFlagPanel({ stock }: RedFlagPanelProps) {
  const flags: RedFlag[] = []

  // Pledge percentage
  const pledge = Number(stock.pledge_pct ?? stock.Pledge_Pct ?? 0)
  if (pledge > 25) {
    flags.push({
      severity: 'CRITICAL',
      label: 'High Promoter Pledge',
      value: `${pledge.toFixed(1)}% pledged`,
      icon: ShieldAlert,
    })
  } else if (pledge > 10) {
    flags.push({
      severity: 'WARNING',
      label: 'Elevated Pledge',
      value: `${pledge.toFixed(1)}% pledged`,
      icon: ShieldAlert,
    })
  }

  // Debt spike
  const de = Number(stock.debt_equity ?? stock.Debt_Equity ?? 0)
  if (de > 2.0) {
    flags.push({
      severity: 'CRITICAL',
      label: 'Dangerous Debt Level',
      value: `D/E ${de.toFixed(2)}`,
      icon: AlertTriangle,
    })
  } else if (de > 1.0) {
    flags.push({
      severity: 'WARNING',
      label: 'Elevated Debt',
      value: `D/E ${de.toFixed(2)}`,
      icon: AlertTriangle,
    })
  }

  // Low promoter holding
  const promHolding = Number(stock.promoter_holding ?? stock['Promoter_Holding%'] ?? 100)
  if (promHolding < 25) {
    flags.push({
      severity: 'CRITICAL',
      label: 'Low Promoter Holding',
      value: `${promHolding.toFixed(1)}%`,
      icon: Users,
    })
  } else if (promHolding < 40) {
    flags.push({
      severity: 'WARNING',
      label: 'Below-Average Promoter Holding',
      value: `${promHolding.toFixed(1)}%`,
      icon: Users,
    })
  }

  // Weak cash quality
  const cfo = Number(stock.cfo_pat_ratio ?? stock.CFO_PAT_Ratio ?? 1)
  if (cfo < 0.3) {
    flags.push({
      severity: 'CRITICAL',
      label: 'Extremely Weak Cash Quality',
      value: `CFO/PAT ${cfo.toFixed(2)}`,
      icon: TrendingDown,
    })
  } else if (cfo < 0.7) {
    flags.push({
      severity: 'WARNING',
      label: 'Below-Par Cash Quality',
      value: `CFO/PAT ${cfo.toFixed(2)}`,
      icon: TrendingDown,
    })
  }

  // Overvaluation
  const pe = Number(stock.pe_ratio ?? stock.PE_Ratio ?? 0)
  if (pe > 80) {
    flags.push({
      severity: 'CRITICAL',
      label: 'Extreme Overvaluation',
      value: `PE ${pe.toFixed(1)}`,
      icon: AlertTriangle,
    })
  } else if (pe > 50) {
    flags.push({
      severity: 'WARNING',
      label: 'Stretched Valuation',
      value: `PE ${pe.toFixed(1)}`,
      icon: AlertTriangle,
    })
  }
  
  // Data Quality Audit
  if (stock.data_quality_flags) {
    flags.push({
      severity: 'CRITICAL',
      label: 'Data Integrity Audit Failure',
      value: Array.isArray(stock.data_quality_flags)
        ? stock.data_quality_flags.join(', ')
        : String(stock.data_quality_flags || ''),
      icon: ShieldAlert,
    })
  }

  if (flags.length === 0) return null

  const criticalCount = flags.filter(f => f.severity === 'CRITICAL').length

  return (
    <div className={`brutalist-card p-5 border-l-4 ${criticalCount > 0 ? 'border-l-brand-rose' : 'border-l-brand-gold'}`}>
      <div className="flex items-center gap-2 mb-4">
        <AlertTriangle className={`h-4 w-4 ${criticalCount > 0 ? 'text-brand-rose' : 'text-brand-gold'}`} />
        <h3 className="font-mono text-xs font-bold uppercase tracking-widest text-brand-text-dim">
          Red Flags ({flags.length})
        </h3>
      </div>

      <div className="space-y-2">
        {flags.map((flag, i) => {
          const Icon = flag.icon
          return (
            <div
              key={i}
              className={`flex items-center gap-3 p-2.5 rounded-lg border ${
                flag.severity === 'CRITICAL'
                  ? 'bg-brand-rose/5 border-brand-rose/20'
                  : 'bg-brand-gold/5 border-brand-gold/10'
              }`}
            >
              <Icon className={`h-4 w-4 flex-shrink-0 ${
                flag.severity === 'CRITICAL' ? 'text-brand-rose' : 'text-brand-gold'
              }`} />
              <div className="flex-1 min-w-0">
                <p className="font-mono text-xs font-bold text-brand-text truncate">{flag.label}</p>
                <p className={`font-mono text-[10px] ${
                  flag.severity === 'CRITICAL' ? 'text-brand-rose' : 'text-brand-gold'
                }`}>{flag.value}</p>
              </div>
              <span className={`px-1.5 py-0.5 rounded text-[8px] font-mono font-bold tracking-widest ${
                flag.severity === 'CRITICAL'
                  ? 'bg-brand-rose/20 text-brand-rose'
                  : 'bg-brand-gold/20 text-brand-gold'
              }`}>
                {flag.severity}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
