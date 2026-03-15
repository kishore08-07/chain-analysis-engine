import React from 'react';
import { CLS_COLORS } from '../../constants/colors';
import { fmtNum, fmtSats } from '../../utils/format';
import Tooltip from '../ui/Tooltip';
import { TT } from '../../constants/tooltips';

export default function DonutChart({ data, colorMap, total }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const sum = entries.reduce((a, [, v]) => a + v, 0);
  if (sum === 0) return <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>No classification data yet</div>;

  const size = 180, cx = size / 2, cy = size / 2, r = 65, thickness = 28;
  const circumference = 2 * Math.PI * r;
  let offset = 0;

  const CLS_TIPS = {
    simple_payment: TT.simple_payment, consolidation: TT.consolidation,
    coinjoin: TT.coinjoin, self_transfer: TT.self_transfer, coinbase: TT.coinbase,
    batch_payment: TT.batch_payment, unknown: TT.unknown,
  };

  return (
    <div className="donut-container">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--surface2)" strokeWidth={thickness} />
        {entries.map(([label, value]) => {
          const dashLen = (value / sum) * circumference;
          const el = (
            <circle key={label} cx={cx} cy={cy} r={r}
              fill="none" stroke={(colorMap[label] || {}).hex || '#8b949e'}
              strokeWidth={thickness}
              strokeDasharray={`${dashLen} ${circumference - dashLen}`}
              strokeDashoffset={-offset}
              transform={`rotate(-90 ${cx} ${cy})`}
              style={{ transition: 'stroke-dasharray 0.5s ease' }}
            />
          );
          offset += dashLen;
          return el;
        })}
        <text x={cx} y={cy - 6} textAnchor="middle" fill="var(--text)" fontSize="22" fontWeight="700">{fmtNum(sum)}</text>
        <text x={cx} y={cy + 14} textAnchor="middle" fill="var(--text-muted)" fontSize="10">transactions</text>
      </svg>
      <div className="donut-legend">
        {entries.map(([label, value]) => (
          <div key={label} className="donut-legend-item">
            <div className="legend-swatch" style={{ background: (colorMap[label] || {}).hex || '#8b949e' }} />
            <span className="legend-label">{label.replace(/_/g, ' ')}</span>
            {CLS_TIPS[label] && <Tooltip text={CLS_TIPS[label]} />}
            <span className="legend-value">
              {fmtNum(value)}{' '}
              <span style={{ color: 'var(--text-dim)', fontWeight: 400 }}>({(value / sum * 100).toFixed(1)}%)</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
