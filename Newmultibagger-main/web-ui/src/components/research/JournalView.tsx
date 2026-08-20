import React from 'react';

const JournalView: React.FC = () => {
  return (
    <div className="p-6 bg-slate-800 rounded-lg shadow">
      <h2 className="text-xl font-bold text-cyan-400 mb-4">Research Journal</h2>
      <p className="text-slate-300">
        Log updates, earnings call notes, and observations. These entries feed into your thesis review.
      </p>
      {/* TODO: Add Journal entries list and form */}
    </div>
  );
};

export default JournalView;
