import React from 'react';

const ThesisView: React.FC = () => {
  return (
    <div className="p-6 bg-slate-800 rounded-lg shadow">
      <h2 className="text-xl font-bold text-cyan-400 mb-4">Investment Theses</h2>
      <p className="text-slate-300">
        Manage core investment theses. Outline growth drivers, expected CAGR, risks, and horizon.
      </p>
      {/* TODO: Add DataGrid/Table for theses, plus a form for new ones */}
    </div>
  );
};

export default ThesisView;
