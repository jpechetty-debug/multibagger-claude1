import React, { useState, useEffect } from 'react';
import ValidationDashboard from '../signals/ValidationDashboard';
import ThesisView from './ThesisView';
import JournalView from './JournalView';
import MemoView from './MemoView';
import KnowledgeBaseView from './KnowledgeBaseView';
import ReviewView from './ReviewView';
import { ShieldAlert, ShieldCheck } from 'lucide-react';

const ResearchDashboard: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'Thesis' | 'Journal' | 'Memos' | 'Knowledge' | 'Reviews'>('Thesis');
  const [trustScore, setTrustScore] = useState<{ trust_score: number; grade: string; passed: boolean } | null>(null);

  useEffect(() => {
    fetch('/api/v1/research/trust-score', {
      headers: { 'X-API-Key': 'DEV_KEY_123' }
    })
      .then(res => res.json())
      .then(data => setTrustScore(data))
      .catch(console.error);
  }, []);

  return (
    <div className="h-[calc(100vh-140px)] bg-slate-900 text-slate-100 flex flex-row overflow-hidden">
      
      {/* LEFT PANEL: Trust Score & Navigation */}
      <div className="w-64 bg-slate-800 border-r border-slate-700 flex flex-col p-4 space-y-6">
        
        {/* Trust Score Widget */}
        <div className="bg-slate-900 border border-slate-700 p-4 rounded-lg">
          <h2 className="text-sm font-bold text-slate-400 mb-2 uppercase tracking-wider">Model Trust Score</h2>
          {trustScore ? (
            <div className="flex items-center justify-between">
              <div>
                <span className={`text-3xl font-black ${trustScore.passed ? 'text-green-400' : 'text-red-400'}`}>
                  {trustScore.trust_score.toFixed(1)}
                </span>
                <span className="text-slate-500 text-xs ml-1">/ 100</span>
              </div>
              <div>
                {trustScore.passed ? (
                  <ShieldCheck className="text-green-400" size={32} />
                ) : (
                  <ShieldAlert className="text-red-400" size={32} />
                )}
              </div>
            </div>
          ) : (
            <div className="text-xs text-slate-500 animate-pulse">Loading...</div>
          )}
          {trustScore && (
            <div className="mt-2 text-xs text-slate-400">
              Grade: <span className="font-bold text-white">{trustScore.grade}</span>
            </div>
          )}
        </div>

        {/* Navigation */}
        <nav className="flex flex-col space-y-2">
          {['Thesis', 'Journal', 'Memos', 'Knowledge', 'Reviews'].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab as any)}
              className={`text-left px-3 py-2 rounded-md font-medium text-sm transition-colors ${
                activeTab === tab ? 'bg-cyan-900 text-cyan-300' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700'
              }`}
            >
              {tab}
            </button>
          ))}
        </nav>
      </div>

      {/* CENTER PANEL: Main Research Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <main className="flex-1 overflow-auto p-4 bg-slate-900">
          {activeTab === 'Thesis' && <ThesisView />}
          {activeTab === 'Journal' && <JournalView />}
          {activeTab === 'Memos' && <MemoView />}
          {activeTab === 'Knowledge' && <KnowledgeBaseView />}
          {activeTab === 'Reviews' && <ReviewView />}
        </main>
      </div>

      {/* RIGHT PANEL: Validation Metrics */}
      <div className="w-96 bg-slate-800 border-l border-slate-700 overflow-y-auto hidden xl:block">
        <div className="p-4 border-b border-slate-700">
          <h2 className="text-sm font-bold text-slate-400 uppercase tracking-wider">Validation Metrics</h2>
        </div>
        <div className="p-4">
          <ValidationDashboard />
        </div>
      </div>
    </div>
  );
};

export default ResearchDashboard;
