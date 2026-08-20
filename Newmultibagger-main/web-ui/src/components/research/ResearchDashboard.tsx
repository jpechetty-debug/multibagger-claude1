import React, { useState } from 'react';
import ValidationDashboard from '../signals/ValidationDashboard';
import ThesisView from './ThesisView';
import JournalView from './JournalView';
import MemoView from './MemoView';
import KnowledgeBaseView from './KnowledgeBaseView';
import ReviewView from './ReviewView';
import { Beaker, BookOpen, FileText, CheckSquare, Target } from 'lucide-react';

type SubTab = 'Validation' | 'Thesis' | 'Journal' | 'Memos' | 'Knowledge' | 'Reviews';

const ResearchDashboard: React.FC = () => {
  const [activeSubTab, setActiveSubTab] = useState<SubTab>('Thesis');

  return (
    <div className="flex flex-col h-full bg-slate-900 text-slate-100">
      {/* Sub-navigation Header */}
      <header className="flex-none p-4 bg-slate-800 border-b border-slate-700 flex space-x-6">
        {[
          { id: 'Thesis', icon: Target, label: 'Thesis' },
          { id: 'Journal', icon: BookOpen, label: 'Journal' },
          { id: 'Memos', icon: FileText, label: 'Memos' },
          { id: 'Knowledge', icon: Beaker, label: 'Knowledge Base' },
          { id: 'Reviews', icon: CheckSquare, label: 'Reviews' },
          { id: 'Validation', icon: Beaker, label: 'Validation (Archived)' },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeSubTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveSubTab(tab.id as SubTab)}
              className={`flex items-center space-x-2 px-3 py-2 rounded-md font-medium text-sm transition-colors ${
                isActive ? 'bg-cyan-900 text-cyan-300' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700'
              }`}
            >
              <Icon size={16} />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </header>

      {/* Main Content Area */}
      <main className="flex-1 overflow-auto p-4">
        {activeSubTab === 'Validation' && <ValidationDashboard />}
        {activeSubTab === 'Thesis' && <ThesisView />}
        {activeSubTab === 'Journal' && <JournalView />}
        {activeSubTab === 'Memos' && <MemoView />}
        {activeSubTab === 'Knowledge' && <KnowledgeBaseView />}
        {activeSubTab === 'Reviews' && <ReviewView />}
      </main>
    </div>
  );
};

export default ResearchDashboard;
