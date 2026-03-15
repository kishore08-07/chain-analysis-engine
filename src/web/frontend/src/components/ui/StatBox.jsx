import React from 'react';
import Tooltip from './Tooltip';
import { fmtNum } from '../../utils/format';

export default function StatBox({ value, label, color, raw, tip }) {
  return (
    <div className="stat-box">
      <div className="value" style={color ? { color } : {}}>
        {raw ? value : fmtNum(value)}
      </div>
      <div className="label">
        {label}
        {tip && <Tooltip text={tip} />}
      </div>
    </div>
  );
}
