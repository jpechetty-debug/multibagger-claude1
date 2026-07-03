import { ReactNode } from 'react'
import { Tooltip } from '../ui/Tooltip'

const METRIC_DICT: Record<string, string> = {
  'F-Score': "Piotroski F-Score (0-9). Measures fundamental health based on profitability, leverage, liquidity, and operating efficiency. 7-9 is exceptional.",
  'QARP': "Quality At a Reasonable Price. Combines high profitability (ROE/ROCE) and growth with sensible valuation multiples.",
  'Sigmoid': "Machine Learning confidence output normalized to a smooth curve. Measures probability of structural outperformance.",
  'Conviction': "Aggregated Sovereign score integrating quantitative fundamentals, momentum, and technical signals.",
  'Margin of Safety': "The percentage difference between the aggregated intrinsic value (DCF/Graham/EPV models) and the current market price.",
  '5Y CAGR': "Compound Annual Growth Rate over the last 5 years. Shows structural sales expansion capability.",
  'ROE': "Return on Equity. Measures how effectively management uses shareholders' capital to generate net profits.",
  'P/E Ratio': "Price to Earnings ratio. Evaluates the current share price relative to its per-share earnings."
}

interface MetricExplainerProps {
  metric: string
  label?: string
  children: ReactNode
}

export function MetricExplainer({ metric, label, children }: MetricExplainerProps) {
  const explainer = METRIC_DICT[metric]
  
  if (!explainer) {
    return <span className="inline-block">{children}</span>
  }

  const tooltipContent = (
    <div className="text-left font-sans">
      <div className="font-bold text-brand-accent mb-1 font-mono uppercase tracking-tight">{metric}</div>
      <div className="text-brand-text-dim leading-snug">{explainer}</div>
    </div>
  )

  return (
    <Tooltip content={tooltipContent}>
      <span className="inline-flex items-center gap-1 cursor-help border-b border-dashed border-brand-text-dim/50 hover:border-brand-accent/70 transition-colors pb-0.5">
        {label && <span className="font-mono text-[10px] uppercase text-brand-text-dim">{label}:</span>}
        {children}
      </span>
    </Tooltip>
  )
}
