import React, { useState } from 'react';

const ReviewView: React.FC = () => {
  return (
    <div className="p-6 bg-slate-800 rounded-lg shadow">
      <h2 className="text-xl font-bold text-cyan-400 mb-4">Quarterly Reviews</h2>
      <p className="text-slate-300 mb-6">
        Compare current realities against original assumptions.
      </p>

      {/* TODO: Add Quarterly review tables and trigger buttons */}
      <div className="bg-slate-900 p-4 rounded border border-slate-700">
        <h3 className="text-lg font-medium text-slate-100 mb-2">Review Status</h3>
        <p className="text-sm text-slate-400">Select a thesis to view its health score and status.</p>
      </div>
    </div>
  );
};

export default ReviewView;
