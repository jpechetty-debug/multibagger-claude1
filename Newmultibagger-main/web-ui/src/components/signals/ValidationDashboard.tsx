import { useEffect, useState } from 'react'
import { api, getApiErrorMessage } from '../../lib/api'

interface ValidationData {
  trust: any;
  holdout: any;
  regime: any;
  shap: any;
  stability: any;
  ablation: any;
  compounder: any;
}

export function ValidationDashboard() {
  const [data, setData] = useState<ValidationData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      try {
        const res = await fetch('/api/validation/dashboard', {
          headers: { 'X-API-Key': 'dev_key_123' }
        });
        if (!res.ok) throw new Error('Failed to fetch validation data');
        const json = await res.json();
        setData(json);
      } catch (err) {
        setError(getApiErrorMessage(err))
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  if (loading) {
    return <div className="p-8 text-brand-primary font-mono text-sm">Loading validation audits...</div>
  }

  if (error) {
    return <div className="p-8 text-brand-rose font-mono text-sm">{error}</div>
  }

  if (!data) return null;

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-12 pb-32">
      <header className="space-y-2">
        <h1 className="text-3xl font-black uppercase tracking-widest text-brand-text">Sovereign Validation Audit</h1>
        <p className="text-brand-text-dim font-mono text-sm">Institutional Grade ML Validation</p>
      </header>

      {/* Trust Score */}
      <section className="glass-panel p-6 space-y-4">
        <h2 className="text-xl font-bold text-brand-primary">Composite Trust Score</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-brand-bg/50 p-4 rounded-lg">
            <div className="text-[10px] uppercase text-brand-text-dim mb-1">Total Score</div>
            <div className={`text-2xl font-black ${data.trust?.score > 70 ? 'text-brand-emerald' : 'text-brand-rose'}`}>
              {data.trust?.score?.toFixed(1) || '0.0'} / 100
            </div>
          </div>
          <div className="bg-brand-bg/50 p-4 rounded-lg">
            <div className="text-[10px] uppercase text-brand-text-dim mb-1">Passed Checks</div>
            <div className="text-2xl font-black text-brand-text">
              {data.trust?.passed_checks || 0} / 6
            </div>
          </div>
        </div>
        
        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-2">
            {data.trust?.details && Object.entries(data.trust.details).map(([k, v]: [string, any]) => (
                <div key={k} className="flex justify-between items-center text-sm font-mono bg-brand-bg/30 p-2 rounded">
                    <span className="capitalize">{k.replace('_', ' ')}</span>
                    <span className={v.passed ? 'text-brand-emerald' : 'text-brand-rose'}>{v.passed ? 'PASS' : 'FAIL'}</span>
                </div>
            ))}
        </div>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Holdout */}
          <section className="glass-panel p-6 space-y-4">
            <h2 className="text-xl font-bold text-brand-primary">Holdout Validation (2018-2020)</h2>
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-brand-bg/50 p-4 rounded-lg">
                <div className="text-[10px] uppercase text-brand-text-dim mb-1">Top 20 CAGR</div>
                <div className="text-xl font-bold text-brand-emerald">
                  {(data.holdout?.metrics?.top20_cagr * 100).toFixed(1)}%
                </div>
              </div>
              <div className="bg-brand-bg/50 p-4 rounded-lg">
                <div className="text-[10px] uppercase text-brand-text-dim mb-1">Max Drawdown</div>
                <div className="text-xl font-bold text-brand-rose">
                  {(data.holdout?.metrics?.top20_max_dd * 100).toFixed(1)}%
                </div>
              </div>
              <div className="bg-brand-bg/50 p-4 rounded-lg">
                <div className="text-[10px] uppercase text-brand-text-dim mb-1">Hit Rate</div>
                <div className="text-xl font-bold text-brand-text">
                  {(data.holdout?.metrics?.hit_rate * 100).toFixed(1)}%
                </div>
              </div>
              <div className="bg-brand-bg/50 p-4 rounded-lg">
                <div className="text-[10px] uppercase text-brand-text-dim mb-1">Top 20 Sharpe</div>
                <div className="text-xl font-bold text-brand-text">
                  {data.holdout?.metrics?.top20_sharpe?.toFixed(2)}
                </div>
              </div>
            </div>
          </section>

          {/* Regime */}
          <section className="glass-panel p-6 space-y-4">
            <h2 className="text-xl font-bold text-brand-primary">Regime Performance</h2>
            <div className="space-y-2">
                {data.regime?.charts?.regime_cagr && Object.entries(data.regime.charts.regime_cagr).map(([regime, cagr]: [string, any]) => (
                    <div key={regime} className="flex justify-between items-center bg-brand-bg/50 p-3 rounded-lg">
                        <span className="font-mono text-sm">{regime}</span>
                        <span className={`font-bold ${cagr > 0 ? 'text-brand-emerald' : 'text-brand-rose'}`}>
                            {(cagr * 100).toFixed(1)}%
                        </span>
                    </div>
                ))}
            </div>
          </section>

          {/* Compounders */}
          <section className="glass-panel p-6 space-y-4">
            <h2 className="text-xl font-bold text-brand-primary">Compounder Capture</h2>
            <div className="grid grid-cols-2 gap-4 mb-4">
                <div className="bg-brand-bg/50 p-4 rounded-lg">
                    <div className="text-[10px] uppercase text-brand-text-dim mb-1">Capture Rate</div>
                    <div className="text-xl font-bold text-brand-emerald">
                        {(data.compounder?.metrics?.capture_rate * 100).toFixed(1)}%
                    </div>
                </div>
                <div className="bg-brand-bg/50 p-4 rounded-lg">
                    <div className="text-[10px] uppercase text-brand-text-dim mb-1">Total Found</div>
                    <div className="text-xl font-bold text-brand-text">
                        {data.compounder?.metrics?.found_compounders} / {data.compounder?.metrics?.total_compounders}
                    </div>
                </div>
            </div>
            
            <div className="text-sm font-mono text-brand-text-dim space-y-1">
                {data.compounder?.charts?.captured_list?.map((sym: string) => (
                    <span key={sym} className="inline-block bg-brand-bg/80 px-2 py-1 rounded mr-2 mb-2">{sym}</span>
                ))}
            </div>
          </section>
          
          {/* Feature Stability */}
          <section className="glass-panel p-6 space-y-4">
            <h2 className="text-xl font-bold text-brand-primary">Feature Stability (KS Test)</h2>
            <div className="bg-brand-bg/50 p-4 rounded-lg">
                <div className="text-[10px] uppercase text-brand-text-dim mb-1">Drifted Features</div>
                <div className="text-xl font-bold text-brand-rose">
                    {data.stability?.metrics?.drifted_features_count || 0}
                </div>
            </div>
            {data.stability?.metrics?.drifted_features_count > 0 && (
                <div className="text-sm font-mono text-brand-text-dim mt-2">
                    {data.stability?.charts?.drifted_features?.map((f: any) => (
                        <div key={f.feature} className="flex justify-between py-1 border-b border-white/5 last:border-0">
                            <span>{f.feature}</span>
                            <span className="text-brand-rose">p={f.p_value.toFixed(4)}</span>
                        </div>
                    ))}
                </div>
            )}
          </section>

          {/* Explainability */}
          <section className="glass-panel p-6 space-y-4 lg:col-span-2">
            <h2 className="text-xl font-bold text-brand-primary">Explainability (SHAP Top Features)</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {data.shap?.charts?.global_importance && Object.entries(data.shap.charts.global_importance).slice(0, 8).map(([feature, imp]: [string, any]) => (
                    <div key={feature} className="bg-brand-bg/50 p-3 rounded-lg flex flex-col justify-between">
                        <span className="text-[10px] uppercase text-brand-text-dim truncate" title={feature}>{feature}</span>
                        <span className="font-mono text-brand-emerald">{imp.toFixed(4)}</span>
                    </div>
                ))}
            </div>
          </section>
      </div>
    </div>
  )
}

export default ValidationDashboard;
