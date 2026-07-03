import { useState, useEffect } from 'react';
import {
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ComposedChart,
  LineChart,
} from 'recharts';
import { AlertTriangle, TrendingUp, TrendingDown, Info, Zap, Activity } from 'lucide-react';
import { api } from '../../lib/api';
import type { QuarterlyTimeline as QuarterlyTimelineType } from '../../lib/contracts';

interface QuarterlyTimelineProps {
  symbol: string;
}

function QuarterlyTimeline({ symbol }: QuarterlyTimelineProps) {
  const [data, setData] = useState<QuarterlyTimelineType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'revenue' | 'profit' | 'margin' | 'combined'>('revenue');

  useEffect(() => {
    async function fetchData() {
      setLoading(true);
      try {
        const result = await api.getQuarterlyTimeline(symbol);
        setData(result);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to fetch quarterly data');
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, [symbol]);

  if (loading) {
    return (
      <div className="brutalist-card p-12 flex flex-col items-center justify-center bg-brand-bg/50 border-dashed">
        <div className="animate-spin text-brand-accent mb-4">
          <Zap size={32} />
        </div>
        <p className="font-mono text-xs uppercase tracking-widest text-brand-text-dim">Reconstructing Financial Timeline...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="brutalist-card p-8 border-brand-rose/30 bg-brand-rose/5">
        <div className="flex items-center gap-3 text-brand-rose mb-4">
          <AlertTriangle size={20} />
          <h3 className="font-mono font-bold uppercase tracking-widest text-sm">Data Link Severed</h3>
        </div>
        <p className="font-mono text-xs text-brand-text-dim">{error || 'No quarterly data available for this terminal node.'}</p>
      </div>
    );
  }

  const quarters = data?.quarters || [];
  const trends = data?.trends || {};
  const alerts = data?.alerts || [];

  const chartData = quarters.map(q => ({
    quarter: q.quarter,
    revenue: q.revenue,
    profit: q.profit,
    revenue_growth: q.revenue_growth_qoq,
    profit_growth: q.profit_growth_qoq,
    margin: q.margin,
    ebitda_margin: q.ebitda_margin,
  }));

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-brand-bg border-2 border-brand-border p-3 font-mono text-[10px] shadow-xl">
          <p className="text-brand-accent font-bold mb-2 border-b border-white/10 pb-1">{label}</p>
          {payload.map((entry: any, index: number) => (
            <div key={index} className="flex justify-between gap-4 mb-1">
              <span style={{ color: entry.color }} className="uppercase">
                {entry.name}:
              </span>
              <span className="text-brand-text font-bold">
                {entry.value.toLocaleString()}{entry.name.includes('%') ? '%' : ' Cr'}
              </span>
            </div>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h3 className="font-mono text-sm font-bold uppercase tracking-widest text-brand-text-dim mb-1 flex items-center gap-2">
            <TrendingUp size={16} /> Quarterly Performance Matrix
          </h3>
          <p className="text-xs font-mono text-brand-text-dim">Trailing 12 Quarter Audit Feed</p>
        </div>

        <div className="flex gap-1 p-1 bg-black/40 border border-white/5">
          {(['revenue', 'profit', 'margin', 'combined'] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              className={`px-3 py-1.5 font-mono text-[10px] uppercase tracking-tighter transition-all ${
                viewMode === mode
                  ? 'bg-brand-accent text-brand-bg font-black'
                  : 'text-brand-text-dim hover:text-brand-text hover:bg-white/5'
              }`}
            >
              {mode}
            </button>
          ))}
        </div>
      </div>

      {/* Chart Section */}
      <div className="brutalist-card p-6 bg-black/20">
        <div className="h-80 w-full">
          <ResponsiveContainer width="100%" height="100%">
            {viewMode === 'margin' ? (
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis 
                  dataKey="quarter" 
                  stroke="rgba(255,255,255,0.2)" 
                  tick={{ fill: '#6d7fa8', fontSize: 10, fontFamily: 'Geist Mono' }} 
                />
                <YAxis 
                  stroke="rgba(255,255,255,0.2)" 
                  tick={{ fill: '#6d7fa8', fontSize: 10, fontFamily: 'Geist Mono' }} 
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend iconType="rect" wrapperStyle={{ fontFamily: 'Geist Mono', fontSize: '10px', paddingTop: '20px' }} />
                <Line
                  type="monotone"
                  dataKey="margin"
                  name="NET MARGIN %"
                  stroke="#FFD700" 
                  strokeWidth={3}
                  dot={{ r: 4, fill: '#FFD700', strokeWidth: 0 }}
                  activeDot={{ r: 6 }}
                />
                <Line
                  type="monotone"
                  dataKey="ebitda_margin"
                  name="EBITDA MARGIN %"
                  stroke="#00ffa3"
                  strokeWidth={2}
                  strokeDasharray="5 5"
                  dot={{ r: 3, fill: '#00ffa3', strokeWidth: 0 }}
                />
              </LineChart>
            ) : (
              <ComposedChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis 
                  dataKey="quarter" 
                  stroke="rgba(255,255,255,0.2)" 
                  tick={{ fill: '#6d7fa8', fontSize: 10, fontFamily: 'Geist Mono' }} 
                />
                <YAxis 
                  yAxisId="left"
                  stroke="rgba(255,255,255,0.2)" 
                  tick={{ fill: '#6d7fa8', fontSize: 10, fontFamily: 'Geist Mono' }} 
                />
                <YAxis 
                  yAxisId="right"
                  orientation="right"
                  stroke="rgba(255,171,0,0.2)" 
                  tick={{ fill: '#ffab00', fontSize: 10, fontFamily: 'Geist Mono' }} 
                  domain={[-100, (data: number) => Math.max(100, data)]}
                />
                <Tooltip content={<CustomTooltip />} />
                <Legend iconType="rect" wrapperStyle={{ fontFamily: 'Geist Mono', fontSize: '10px', paddingTop: '20px' }} />
                
                {viewMode === 'revenue' && (
                  <>
                    <Bar yAxisId="left" dataKey="revenue" name="REVENUE (CR)" fill="#3b82f6" fillOpacity={0.6} />
                    <Line yAxisId="right" type="monotone" dataKey="revenue_growth" name="QOQ GROWTH %" stroke="#ffab00" strokeWidth={2} dot={{ r: 4 }} />
                  </>
                )}
                
                {viewMode === 'profit' && (
                  <>
                    <Bar yAxisId="left" dataKey="profit" name="NET PROFIT (CR)" fill="#00ffa3" fillOpacity={0.6} />
                    <Line yAxisId="right" type="monotone" dataKey="profit_growth" name="QOQ GROWTH %" stroke="#ffab00" strokeWidth={2} dot={{ r: 4 }} />
                  </>
                )}
                
                {viewMode === 'combined' && (
                  <>
                    <Bar yAxisId="left" dataKey="revenue" name="REVENUE" fill="#3b82f6" fillOpacity={0.4} />
                    <Bar yAxisId="left" dataKey="profit" name="PROFIT" fill="#00ffa3" fillOpacity={0.4} />
                    <Line yAxisId="right" type="monotone" dataKey="margin" name="MARGIN %" stroke="#FFD700" strokeWidth={2} dot={{ r: 4 }} />
                  </>
                )}
              </ComposedChart>
            )}
          </ResponsiveContainer>
        </div>
      </div>

      {/* Analytics & Alerts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Alerts & Insights */}
        <div className="brutalist-card p-5 border-white/5 bg-black/40">
           <h4 className="font-mono text-[10px] font-bold uppercase tracking-widest text-brand-text-dim mb-4 flex items-center gap-2">
             <Info size={14} className="text-brand-accent" /> Intelligence Alerts
           </h4>
           <div className="space-y-3">
             {alerts.length > 0 ? (
               alerts.map((alert, idx) => (
                 <div 
                   key={idx} 
                   className={`p-3 border flex gap-3 items-start transition-all hover:translate-x-1 ${
                     alert.type === 'POSITIVE' ? 'border-brand-accent/20 bg-brand-accent/5 text-brand-accent' :
                     alert.type === 'WARNING' ? 'border-brand-gold/20 bg-brand-gold/5 text-brand-gold' :
                     'border-brand-rose/20 bg-brand-rose/5 text-brand-rose'
                   }`}
                 >
                   <div className="mt-0.5">
                     {alert.type === 'POSITIVE' ? <TrendingUp size={14} /> : 
                      alert.type === 'WARNING' ? <AlertTriangle size={14} /> : <TrendingDown size={14} />}
                   </div>
                   <p className="font-mono text-[11px] leading-tight uppercase tracking-tight">{alert.message}</p>
                 </div>
               ))
             ) : (
               <div className="p-3 border border-dashed border-white/10 text-brand-text-dim font-mono text-[10px] uppercase">
                 No critical anomalies detected in timeline.
               </div>
             )}
           </div>
        </div>

        {/* Trend Summary */}
        <div className="brutalist-card p-5 border-white/5 bg-black/40">
           <h4 className="font-mono text-[10px] font-bold uppercase tracking-widest text-brand-text-dim mb-4 flex items-center gap-2">
             <Activity size={14} className="text-brand-gold" /> Trend Synthesis
           </h4>
           <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <span className="font-mono text-[9px] uppercase text-brand-text-dim block">Revenue Trend</span>
                <span className={`font-mono text-xs font-bold uppercase ${trends.revenue_trend === 'GROWING' ? 'text-brand-accent' : trends.revenue_trend === 'DECLINING' ? 'text-brand-rose' : 'text-brand-gold'}`}>
                  {trends.revenue_trend}
                </span>
              </div>
              <div className="space-y-1">
                <span className="font-mono text-[9px] uppercase text-brand-text-dim block">Avg QoQ Growth</span>
                <span className="font-mono text-xs font-bold uppercase text-brand-text">
                  {trends.avg_revenue_growth}%
                </span>
              </div>
              <div className="space-y-1">
                <span className="font-mono text-[9px] uppercase text-brand-text-dim block">Margin Status</span>
                <span className={`font-mono text-xs font-bold uppercase ${trends.margin_trend === 'EXPANDING' ? 'text-brand-accent' : trends.margin_trend === 'CONTRACTING' ? 'text-brand-rose' : 'text-brand-text'}`}>
                  {trends.margin_trend}
                </span>
              </div>
              <div className="space-y-1">
                <span className="font-mono text-[9px] uppercase text-brand-text-dim block">Compounding Velocity</span>
                <span className={`font-mono text-xs font-bold uppercase ${trends.consistency === 'HIGH' ? 'text-brand-accent' : 'text-brand-gold'}`}>
                  {trends.consistency}
                </span>
              </div>
           </div>
           
           <div className="mt-6 pt-4 border-t border-white/5">
              <div className="flex justify-between items-center mb-1">
                <span className="font-mono text-[9px] uppercase text-brand-text-dim">Growth Consistency</span>
                <span className="font-mono text-[9px] uppercase text-brand-text-dim">{trends.quarters_with_growth}/{trends.total_quarters} Qtrs</span>
              </div>
              <div className="h-1 bg-white/5 overflow-hidden">
                <div 
                  className="h-full bg-brand-accent shadow-[0_0_8px_rgba(0,255,163,0.5)]" 
                  style={{ width: `${(trends.quarters_with_growth / trends.total_quarters) * 100}%` }}
                />
              </div>
           </div>
        </div>
      </div>

      {/* Data Grid (Table) */}
      <div className="brutalist-card overflow-hidden bg-black/20">
         <div className="overflow-x-auto">
            <table className="w-full text-left font-mono text-[10px]">
               <thead>
                  <tr className="bg-white/5 border-b border-white/10">
                     <th className="p-3 uppercase tracking-widest text-brand-text-dim font-bold">Quarter</th>
                     <th className="p-3 text-right uppercase tracking-widest text-brand-text-dim font-bold">Revenue (Cr)</th>
                     <th className="p-3 text-right uppercase tracking-widest text-brand-text-dim font-bold">Growth %</th>
                     <th className="p-3 text-right uppercase tracking-widest text-brand-text-dim font-bold">Profit (Cr)</th>
                     <th className="p-3 text-right uppercase tracking-widest text-brand-text-dim font-bold">Margin %</th>
                     <th className="p-3 text-right uppercase tracking-widest text-brand-text-dim font-bold">EPS</th>
                  </tr>
               </thead>
               <tbody className="divide-y divide-white/5">
                  {quarters.map((q, idx) => (
                    <tr key={idx} className="hover:bg-white/5 transition-colors group">
                       <td className="p-3 font-bold group-hover:text-brand-accent">{q.quarter}</td>
                       <td className="p-3 text-right">Rs {q.revenue.toLocaleString()}</td>
                       <td className={`p-3 text-right font-bold ${
                         (q.revenue_growth_qoq ?? 0) > 0 ? 'text-brand-accent' : (q.revenue_growth_qoq ?? 0) < 0 ? 'text-brand-rose' : 'text-brand-text-dim'
                       }`}>
                         {q.revenue_growth_qoq !== null ? `${q.revenue_growth_qoq > 0 ? '+' : ''}${q.revenue_growth_qoq}%` : '-'}
                       </td>
                       <td className="p-3 text-right">Rs {q.profit.toLocaleString()}</td>
                       <td className="p-3 text-right font-bold">{q.margin}%</td>
                       <td className="p-3 text-right text-brand-text-dim">{q.eps ?? '-'}</td>
                    </tr>
                  ))}
               </tbody>
            </table>
         </div>
      </div>
    </div>
  );
}

export default QuarterlyTimeline;
