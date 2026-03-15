import React from 'react';
import { CLS_COLORS } from '../constants/colors';
import { fmtSats } from '../utils/format';

export default function TxFlowDiagram({ inputs, outputs, classification, isCoinbase }) {
  const maxIO = Math.max(inputs, outputs, 1);
  const rowH = 22;
  const padY = 14;
  const h = maxIO * rowH + padY * 2;
  const w = 320;
  const txBoxW = 100;
  const txBoxH = 32;
  const txBoxX = (w - txBoxW) / 2;
  const txBoxY = h / 2 - txBoxH / 2;
  const clsColor = (CLS_COLORS[classification] || {}).hex || '#8b949e';

  const inCount = isCoinbase ? 1 : inputs;
  const inStartY = h / 2 - (inCount - 1) * rowH / 2;
  const outStartY = h / 2 - (outputs - 1) * rowH / 2;

  return (
    <div className="tx-flow">
      <svg width={w} height={h} style={{ display: 'block' }}>
        {/* Input lines */}
        {Array.from({ length: inCount }, (_, i) => {
          const y = inStartY + i * rowH;
          return (
            <g key={`i${i}`}>
              <line x1={24} y1={y} x2={txBoxX} y2={h / 2} className="flow-input-line" />
              <circle cx={20} cy={y} r={4} className="flow-dot-in" />
              <text x={8} y={y + 4} fontSize={9} fill="var(--text-dim)" textAnchor="middle">
                {isCoinbase && i === 0 ? 'CB' : ''}
              </text>
            </g>
          );
        })}

        {/* TX box */}
        <rect x={txBoxX} y={txBoxY} width={txBoxW} height={txBoxH} className="flow-tx-box"
          style={{ stroke: clsColor, strokeWidth: 1.5 }} />
        <text x={w / 2} y={h / 2 + 4} textAnchor="middle" fontSize={11} fontWeight="600" fill={clsColor}>
          {classification.replace(/_/g, ' ').substring(0, 14)}
        </text>

        {/* Output lines */}
        {Array.from({ length: outputs }, (_, i) => {
          const y = outStartY + i * rowH;
          return (
            <g key={`o${i}`}>
              <line x1={txBoxX + txBoxW} y1={h / 2} x2={w - 24} y2={y} className="flow-output-line" />
              <circle cx={w - 20} cy={y} r={4} className="flow-dot-out" />
            </g>
          );
        })}

        {/* Labels */}
        <text x={4} y={12} fontSize={10} fill="var(--text-dim)">Inputs ({inCount})</text>
        <text x={w - 4} y={12} fontSize={10} fill="var(--text-dim)" textAnchor="end">Outputs ({outputs})</text>
      </svg>
    </div>
  );
}
