import React from 'react';
import { CLS_COLORS } from '../constants/colors';
import { TT } from '../constants/tooltips';
import { fmtSats } from '../utils/format';
import Tooltip from './ui/Tooltip';
import TxFlowDiagram from './TxFlowDiagram';

const HEUR_TIP = {
  cioh: TT.cioh, change_detection: TT.change_detection,
  address_reuse: TT.address_reuse, coinjoin: TT.coinjoin_h,
  consolidation: TT.consolidation_h, self_transfer: TT.self_transfer_h,
  peeling_chain: TT.peeling_chain, op_return: TT.op_return,
  round_number_payment: TT.round_number_payment,
};

export default function TxDetail({ tx }) {
  const heuristics = tx.heuristics || {};

  return (
    <div className="tx-detail">
      <div style={{ fontFamily: 'monospace', fontSize: 11, wordBreak: 'break-all', color: 'var(--text-dim)', marginBottom: 14 }}>
        <strong>TXID:</strong> {tx.txid}
        <Tooltip text={TT.txTxid} />
      </div>

      <div className="tx-detail-grid">
        {/* Left: Metadata + Flow */}
        <div>
          <div style={{ marginBottom: 12 }}>
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>Classification</span>
            <Tooltip text={TT.txClassification} />
            {'  '}
            <span className={`badge ${(CLS_COLORS[tx.classification] || {}).cls || 'badge-blue'}`}>
              {tx.classification}
            </span>
            {CLS_COLORS[tx.classification] && (
              <Tooltip text={TT[tx.classification] || ''} />
            )}
          </div>

          {tx.input_count != null && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12 }}>
              <div className="stat-box" style={{ padding: 8 }}>
                <div className="value" style={{ fontSize: 18, color: 'var(--accent)' }}>{tx.input_count}</div>
                <div className="label">Inputs<Tooltip text={TT.txInOut} /></div>
              </div>
              <div className="stat-box" style={{ padding: 8 }}>
                <div className="value" style={{ fontSize: 18, color: 'var(--green)' }}>{tx.output_count}</div>
                <div className="label">Outputs<Tooltip text={TT.txInOut} /></div>
              </div>
            </div>
          )}

          {tx.fee_rate_sat_vb != null && (
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>
              Fee Rate: <strong style={{ color: 'var(--text)' }}>{tx.fee_rate_sat_vb} sat/vB</strong>
              <Tooltip text={TT.txFeeRate} />
            </div>
          )}

          {tx.total_output_value_sats != null && (
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>
              Total Output: <strong style={{ color: 'var(--text)' }}>{fmtSats(tx.total_output_value_sats)}</strong>
            </div>
          )}

          {tx.input_count != null && (
            <TxFlowDiagram inputs={tx.input_count} outputs={tx.output_count}
              classification={tx.classification} isCoinbase={tx.is_coinbase} />
          )}
        </div>

        {/* Right: Heuristic results */}
        <div>
          <h3 style={{ marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
            Detective Results
            <Tooltip text={TT.txHeuristics} />
          </h3>
          <div className="heuristic-grid">
            {Object.entries(heuristics).map(([id, result]) => (
              <div key={id} className={`heuristic-item ${result.detected ? (result.suppressed ? 'suppressed' : 'detected') : 'not-detected'}`}>
                <span className={`dot ${result.detected ? (result.suppressed ? 'suppressed-dot' : 'on') : 'off'}`} />
                <span style={{ fontWeight: 500 }}>{id.replace(/_/g, ' ')}</span>
                {HEUR_TIP[id] && <Tooltip text={HEUR_TIP[id]} />}
                {result.detected && result.suppressed && (
                  <span className="badge badge-orange" style={{ fontSize: 10, marginLeft: 'auto' }}>
                    overridden<Tooltip text={TT.txSuppressed} />
                  </span>
                )}
                {result.detected && !result.suppressed && result.confidence && (
                  <span className={`badge badge-${result.confidence === 'high' ? 'green' : result.confidence === 'medium' ? 'orange' : 'red'}`}
                    style={{ fontSize: 10, marginLeft: 'auto' }}>{result.confidence}</span>
                )}
              </div>
            ))}
          </div>

          {heuristics.change_detection && heuristics.change_detection.detected && (
            <div className="detail-chip" style={{ marginTop: 10 }}>
              <strong>🔄 Change output</strong> detected at index #{heuristics.change_detection.likely_change_index}.
              Method: <em>{heuristics.change_detection.method}</em>
              <Tooltip text={TT.change_detection} />
            </div>
          )}
          {heuristics.op_return && heuristics.op_return.detected && (
            <div className="detail-chip" style={{ marginTop: 8 }}>
              <strong>📝 OP_RETURN</strong> — data embedded permanently in this transaction.
              <Tooltip text={TT.op_return} />
            </div>
          )}
          {heuristics.cioh && heuristics.cioh.detected && heuristics.cioh.suppressed && (
            <div className="detail-chip" style={{ marginTop: 8, borderColor: 'var(--orange)' }}>
              <strong>⚠️ CIOH suppressed</strong> — Common Input Ownership flagged, but CoinJoin overrides it.
              Inputs likely belong to <em>different</em> people.
              <Tooltip text={TT.txSuppressed} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
