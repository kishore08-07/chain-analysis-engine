import React from 'react';
import { fmtNum } from '../../utils/format';
import { HEUR_COLORS } from '../../constants/colors';
import Tooltip from '../ui/Tooltip';
import { TT } from '../../constants/tooltips';

const HEUR_TIP = {
  cioh: TT.cioh,
  change_detection: TT.change_detection,
  address_reuse: TT.address_reuse,
  coinjoin: TT.coinjoin_h,
  consolidation: TT.consolidation_h,
  self_transfer: TT.self_transfer_h,
  peeling_chain: TT.peeling_chain,
  op_return: TT.op_return,
  round_number_payment: TT.round_number_payment,
};

export default function HeuristicBars({ counts, total, heuristics }) {
  const ids = heuristics.length > 0 ? heuristics : Object.keys(counts);
  const sorted = ids.map(id => [id, counts[id] || 0]).sort((a, b) => b[1] - a[1]);
  const max = sorted.length > 0 ? Math.max(sorted[0][1], 1) : 1;

  return (
    <div className="h-bars">
      {sorted.map(([id, count], i) => (
        <div key={id} className="h-bar-row">
          <div className="h-bar-label">
            {id.replace(/_/g, ' ')}
            {HEUR_TIP[id] && <Tooltip text={HEUR_TIP[id]} />}
          </div>
          <div className="h-bar-track">
            <div className="h-bar-fill"
              style={{ width: `${(count / max) * 100}%`, background: HEUR_COLORS[i % HEUR_COLORS.length] }} />
          </div>
          <div className="h-bar-value">{fmtNum(count)} ({total > 0 ? (count / total * 100).toFixed(1) : 0}%)</div>
        </div>
      ))}
    </div>
  );
}
