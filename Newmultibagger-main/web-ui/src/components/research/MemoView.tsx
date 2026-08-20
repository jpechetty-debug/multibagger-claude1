import React from 'react';

const MemoView: React.FC = () => {
  return (
    <div className="p-6 bg-slate-800 rounded-lg shadow">
      <h2 className="text-xl font-bold text-cyan-400 mb-4">Investment Memos</h2>
      <p className="text-slate-300">
        Generate and review deterministic and LLM-driven investment memos.
      </p>
      {/* TODO: Add logic to fetch and display memos */}
    </div>
  );
};

export default MemoView;
