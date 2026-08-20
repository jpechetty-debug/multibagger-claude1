import React from 'react';

const KnowledgeBaseView: React.FC = () => {
  return (
    <div className="p-6 bg-slate-800 rounded-lg shadow">
      <h2 className="text-xl font-bold text-cyan-400 mb-4">Knowledge Base</h2>
      <p className="text-slate-300">
        Review indexed documents, PDFs, and deep dives for your research targets.
      </p>
      {/* TODO: Add knowledge entries viewer */}
    </div>
  );
};

export default KnowledgeBaseView;
