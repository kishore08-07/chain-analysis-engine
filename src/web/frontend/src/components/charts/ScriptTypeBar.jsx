import React from 'react';
import { fmtNum } from '../../utils/format';
import { SCRIPT_COLORS } from '../../constants/colors';
import Tooltip from '../ui/Tooltip';
import { TT } from '../../constants/tooltips';

const SCRIPT_TIP = {
  p2wpkh: TT.p2wpkh, p2tr: TT.p2tr, p2pkh: TT.p2pkh,
  p2sh: TT.p2sh, p2wsh: TT.p2wsh, multisig: TT.multisig,
  op_return: TT.op_return_st, unknown: TT.unknown_st,
};

export default function ScriptTypeBar({ dist }) {
  const entries = Object.entries(dist).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((a, [, v]) => a + v, 0);
  if (total === 0) return null;

  return (
    <div>
      <div className="script-bar">
        {entries.map(([type, count]) => (
          <div key={type}
            style={{ width: `${(count / total) * 100}%`, background: SCRIPT_COLORS[type] || '#8b949e' }}
            title={`${type}: ${fmtNum(count)} (${(count / total * 100).toFixed(1)}%)`}
          />
        ))}
      </div>
      <div className="script-legend">
        {entries.map(([type, count]) => (
          <div key={type} className="script-legend-item">
            <span className="script-swatch" style={{ background: SCRIPT_COLORS[type] || '#8b949e' }} />
            <span style={{ color: 'var(--text-muted)' }}>{type}</span>
            {SCRIPT_TIP[type] && <Tooltip text={SCRIPT_TIP[type]} />}
            <span style={{ fontWeight: 600 }}>{fmtNum(count)}</span>
            <span style={{ color: 'var(--text-dim)' }}>({(count / total * 100).toFixed(1)}%)</span>
          </div>
        ))}
      </div>
    </div>
  );
}
