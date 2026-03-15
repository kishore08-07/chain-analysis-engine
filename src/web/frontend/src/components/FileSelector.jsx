import React from 'react';
import { fmtNum } from '../utils/format';
import { TT } from '../constants/tooltips';
import Tooltip from './ui/Tooltip';

export default function FileSelector({ files, selFile, onSelect, loading }) {
  return (
    <div>
      <div className="section-intro">
        <h2 style={{ marginBottom: 6 }}>
          🗂️ Choose a block file to investigate
          <Tooltip text={TT.file} />
        </h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          Bitcoin Core stores its blockchain in numbered files. Pick one below to see what was recorded inside.
        </p>
      </div>
      <div className="file-list">
        {files.map(f => (
          <div key={f.stem} className={`file-card ${selFile === f.stem ? 'active' : ''}`}
            onClick={() => onSelect(f.stem)}>
            <div className="file-card-top">
              <span className="file-icon">📦</span>
              <span className="file-name">{f.filename}</span>
            </div>
            <div className="meta">
              <span>
                <strong>{f.block_count}</strong> blocks
                <Tooltip text={TT.blocks} />
              </span>
              &middot;
              <span>
                <strong>{fmtNum(f.total_transactions)}</strong> transactions
                <Tooltip text={TT.transactions} />
              </span>
            </div>
            <div style={{ marginTop: 6 }}>
              <span style={{ color: 'var(--red)', fontSize: 13 }}>
                ⚑ {fmtNum(f.flagged_transactions)} flagged
              </span>
              <Tooltip text={TT.flagged} />
            </div>
          </div>
        ))}
        {files.length === 0 && !loading && (
          <div className="empty-state" style={{ gridColumn: '1/-1' }}>
            <div className="icon">🔍</div>
            <p>No analysis files found. Run <code>cli.sh</code> first to analyse block data.</p>
          </div>
        )}
      </div>
    </div>
  );
}
