import React from 'react';
import Tooltip from '../ui/Tooltip';
import { TT } from '../../constants/tooltips';

export default function FeeRateViz({ stats }) {
  if (!stats || !stats.max_sat_vb) return <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>No fee data — undo file may not be available</div>;
  const { min_sat_vb, max_sat_vb, median_sat_vb, mean_sat_vb } = stats;
  const range = max_sat_vb - min_sat_vb || 1;
  const medianPct = ((median_sat_vb - min_sat_vb) / range) * 100;
  const meanPct = ((mean_sat_vb - min_sat_vb) / range) * 100;

  return (
    <div>
      <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(4,1fr)', marginBottom: 12 }}>
        <div className="stat-box">
          <div className="value" style={{ fontSize: 18 }}>{min_sat_vb}</div>
          <div className="label">Min<Tooltip text={TT.feeMin} /></div>
        </div>
        <div className="stat-box">
          <div className="value" style={{ fontSize: 18, color: 'var(--accent)' }}>{median_sat_vb}</div>
          <div className="label">Median<Tooltip text={TT.feeMedian} /></div>
        </div>
        <div className="stat-box">
          <div className="value" style={{ fontSize: 18, color: 'var(--purple)' }}>{mean_sat_vb}</div>
          <div className="label">Mean<Tooltip text={TT.feeMean} /></div>
        </div>
        <div className="stat-box">
          <div className="value" style={{ fontSize: 18 }}>{max_sat_vb}</div>
          <div className="label">Max<Tooltip text={TT.feeMax} /></div>
        </div>
      </div>
      <div className="fee-visual">
        <div className="fee-label">{min_sat_vb}<br />min</div>
        <div className="fee-bar-container">
          <div className="fee-range-bar" style={{ left: '0%', width: '100%' }} />
          <div className="fee-median-marker" style={{ left: `${medianPct}%` }} title={`Median: ${median_sat_vb} sat/vB`} />
          <div className="fee-mean-marker" style={{ left: `${meanPct}%` }} title={`Mean: ${mean_sat_vb} sat/vB`} />
        </div>
        <div className="fee-label">{max_sat_vb}<br />max</div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'center', gap: 20, marginTop: 8, fontSize: 11, color: 'var(--text-dim)' }}>
        <span style={{ color: 'var(--accent)' }}>▎ Median ({median_sat_vb} sat/vB)</span>
        <span style={{ color: 'var(--purple)' }}>┊ Mean ({mean_sat_vb} sat/vB)</span>
      </div>
    </div>
  );
}
