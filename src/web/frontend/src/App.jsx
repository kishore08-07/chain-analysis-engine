import React, { useState } from 'react';
import { useAnalysis } from './hooks/useAnalysis';
import Header from './components/Header';
import FileSelector from './components/FileSelector';
import Dashboard from './components/Dashboard';
import BlockExplorer from './components/BlockExplorer';
import TransactionExplorer from './components/TransactionExplorer';
import LoadingSpinner from './components/ui/LoadingSpinner';

export default function App() {
  const { files, selFile, data, loading, error, loadFile } = useAnalysis();
  const [view, setView] = useState('dashboard');
  const [selBlock, setSelBlock] = useState(0);

  const handleLoadFile = (stem) => {
    loadFile(stem);
    setSelBlock(0);
    setView('dashboard');
  };

  return (
    <div>
      <Header />
      <div className="container" style={{ paddingTop: 24, paddingBottom: 60 }}>
        {/* File selector */}
        <FileSelector files={files} selFile={selFile} onSelect={handleLoadFile} loading={loading} />

        {loading && <LoadingSpinner />}

        {error && (
          <div className="card" style={{ borderColor: 'var(--red)' }}>
            <h2 style={{ color: 'var(--red)' }}>Error</h2>
            <p style={{ color: 'var(--text-muted)' }}>{error}</p>
          </div>
        )}

        {data && !loading && (
          <div>
            {/* View tabs */}
            <div className="view-tabs">
              <div className={`view-tab ${view === 'dashboard' ? 'active' : ''}`} onClick={() => setView('dashboard')}>📊 Dashboard</div>
              <div className={`view-tab ${view === 'blocks' ? 'active' : ''}`} onClick={() => setView('blocks')}>⬛ Blocks</div>
              <div className={`view-tab ${view === 'transactions' ? 'active' : ''}`} onClick={() => setView('transactions')}>💰 Transactions</div>
            </div>

            {view === 'dashboard' && <Dashboard data={data} />}
            {view === 'blocks' && <BlockExplorer data={data} selBlock={selBlock} setSelBlock={setSelBlock} />}
            {view === 'transactions' && <TransactionExplorer data={data} selBlock={selBlock} setSelBlock={setSelBlock} />}
          </div>
        )}
      </div>
    </div>
  );
}
