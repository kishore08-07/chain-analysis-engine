import React from 'react';
import { CLS_COLORS } from '../constants/colors';
import StatBox from './ui/StatBox';
import DonutChart from './charts/DonutChart';
import HeuristicBars from './charts/HeuristicBars';
import ScriptTypeBar from './charts/ScriptTypeBar';
import FeeRateViz from './charts/FeeRateViz';

export default function BlockExplorer({ data, selBlock, setSelBlock }) {
  const blocks = data.blocks || [];
  const block = blocks[selBlock];

  return (
    <div>
      <div className="card">
        <div className="card-header">
          <h2>⬛ Block Explorer ({blocks.length} blocks)</h2>
        </div>
        <div className="block-tabs">
          {blocks.map((b, i) => (
            <div key={i} className={`block-tab ${selBlock === i ? 'active' : ''}`}
              onClick={() => setSelBlock(i)}>
              #{b.block_height || i}
            </div>
          ))}
        </div>
      </div>
      {block && <BlockDetail block={block} />}
    </div>
  );
}

function BlockDetail({ block }) {
  const summary = block.analysis_summary || {};
  const feeStats = summary.fee_rate_stats || {};
  const scriptDist = summary.script_type_distribution || {};
  const classDist = summary.classification_distribution || {};
  const hCounts = summary.heuristic_detection_counts || {};
  const txs = block.transactions || [];
  const hasTxs = txs.length > 0;
  const timestamp = block.timestamp ? new Date(block.timestamp * 1000).toUTCString() : null;

  return (
    <div>
      <div className="card">
        <h2>Block #{block.block_height || '?'}</h2>
        <div style={{ fontSize: 12, color: 'var(--text-dim)', wordBreak: 'break-all', margin: '8px 0 4px', fontFamily: 'monospace' }}>
          {block.block_hash}
        </div>
        {timestamp && <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12 }}>🕗 {timestamp}</div>}
        <div className="stat-grid">
          <StatBox value={block.tx_count} label="Transactions" />
          <StatBox value={summary.flagged_transactions || 0} label="Flagged" color="var(--red)" />
          <StatBox value={feeStats.median_sat_vb || 0} label="Median Fee" />
          <StatBox value={feeStats.mean_sat_vb || 0} label="Mean Fee" />
          <StatBox value={feeStats.min_sat_vb || 0} label="Min Fee" />
          <StatBox value={feeStats.max_sat_vb || 0} label="Max Fee" />
        </div>
      </div>

      <div className="dash-grid">
        {Object.keys(classDist).length > 0 && (
          <div className="card">
            <h3>Classifications</h3>
            <DonutChart data={classDist} colorMap={CLS_COLORS} total={block.tx_count} />
          </div>
        )}
        {Object.keys(hCounts).length > 0 && (
          <div className="card">
            <h3>Heuristic Detections</h3>
            <HeuristicBars counts={hCounts} total={block.tx_count} heuristics={summary.heuristics_applied || []} />
          </div>
        )}
      </div>

      {Object.keys(scriptDist).length > 0 && (
        <div className="card">
          <h3>Script Types</h3>
          <ScriptTypeBar dist={scriptDist} />
        </div>
      )}

      {Object.keys(feeStats).length > 0 && (
        <div className="card">
          <h3>Fee Rate Distribution</h3>
          <FeeRateViz stats={feeStats} />
        </div>
      )}

      {!hasTxs && (
        <div className="card empty-state">
          <div className="icon">📄</div>
          <p>Transaction-level details are available for the first block only. Select Block #0 to explore individual transactions.</p>
        </div>
      )}
    </div>
  );
}
