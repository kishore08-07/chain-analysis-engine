import React, { useState, useMemo, useEffect } from 'react';
import { fmtNum, truncTxid } from '../utils/format';
import { CLS_COLORS } from '../constants/colors';
import { TT } from '../constants/tooltips';
import Tooltip from './ui/Tooltip';
import TxDetail from './TxDetail';

export default function TransactionExplorer({ data, selBlock, setSelBlock }) {
  const blocks = data.blocks || [];
  const txBlocks = blocks.map((b, i) => ({ ...b, idx: i })).filter(b => (b.transactions || []).length > 0);

  if (txBlocks.length === 0) {
    return (
      <div className="card empty-state">
        <div className="icon">💰</div>
        <p>No transaction-level data available.</p>
      </div>
    );
  }

  const block = txBlocks[0];
  return <TransactionList txs={block.transactions || []} blockHeight={block.block_height} />;
}

function TransactionList({ txs, blockHeight }) {
  const [search, setSearch] = useState('');
  const [classFilter, setClassFilter] = useState('all');
  const [heurFilter, setHeurFilter] = useState('all');
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [expandedTx, setExpandedTx] = useState(null);
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 50;

  const heurIds = useMemo(() => {
    if (txs.length === 0) return [];
    return Object.keys(txs[0].heuristics || {});
  }, [txs]);

  const classifications = useMemo(() => {
    const s = new Set(txs.map(t => t.classification));
    return Array.from(s).sort();
  }, [txs]);

  const classCounts = useMemo(() => {
    const c = {};
    txs.forEach(t => { c[t.classification] = (c[t.classification] || 0) + 1; });
    return c;
  }, [txs]);

  const filtered = useMemo(() => {
    return txs.filter(tx => {
      if (search && !tx.txid.toLowerCase().includes(search.toLowerCase())) return false;
      if (classFilter !== 'all' && tx.classification !== classFilter) return false;
      if (heurFilter !== 'all') {
        const h = (tx.heuristics || {})[heurFilter];
        if (!h || !h.detected) return false;
      }
      if (flaggedOnly) {
        if (!Object.values(tx.heuristics || {}).some(h => h.detected)) return false;
      }
      return true;
    });
  }, [txs, search, classFilter, heurFilter, flaggedOnly]);

  const pageCount = Math.ceil(filtered.length / PAGE_SIZE);
  const pageTxs = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  useEffect(() => { setPage(0); }, [search, classFilter, heurFilter, flaggedOnly]);

  return (
    <div>
      <div className="card">
        <div className="card-header">
          <h2>💰 Transactions — Block #{blockHeight}</h2>
          <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>{fmtNum(filtered.length)} of {fmtNum(txs.length)}</span>
        </div>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 14 }}>
          Click any row to expand the full detective report for that transaction. Use the filters below to narrow down.
        </p>
        {/* Classification pills */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 14 }}>
          {Object.entries(classCounts).sort((a, b) => b[1] - a[1]).map(([cls, count]) => (
            <span key={cls}
              className={`badge ${(CLS_COLORS[cls] || {}).cls || 'badge-blue'}`}
              style={{ cursor: 'pointer', opacity: classFilter !== 'all' && classFilter !== cls ? 0.4 : 1 }}
              onClick={() => setClassFilter(classFilter === cls ? 'all' : cls)}>
              {cls.replace(/_/g, ' ')}: {fmtNum(count)}
            </span>
          ))}
        </div>

        {/* Filter bar */}
        <div className="filter-bar">
          <input type="text" placeholder="🔍 Search by txid..." value={search}
            onChange={e => setSearch(e.target.value)} />
          <select value={classFilter} onChange={e => setClassFilter(e.target.value)}>
            <option value="all">All classifications</option>
            {classifications.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <select value={heurFilter} onChange={e => setHeurFilter(e.target.value)}>
            <option value="all">All heuristics</option>
            {heurIds.map(h => <option key={h} value={h}>{h.replace(/_/g, ' ')}</option>)}
          </select>
          <button className={`btn ${flaggedOnly ? 'active' : ''}`}
            onClick={() => setFlaggedOnly(!flaggedOnly)}>
            ⚑ Flagged only
          </button>
        </div>

        {/* Transaction table */}
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th style={{ width: 40 }}>#</th>
                <th>TXID <Tooltip text={TT.txTxid} /></th>
                <th>Classification <Tooltip text={TT.txClassification} /></th>
                <th>In/Out <Tooltip text={TT.txInOut} /></th>
                <th>Fee Rate <Tooltip text={TT.txFeeRate} /></th>
                <th>Heuristics <Tooltip text={TT.txHeuristics} /></th>
              </tr>
            </thead>
            <tbody>
              {pageTxs.map((tx, i) => {
                const idx = page * PAGE_SIZE + i;
                const detected = Object.entries(tx.heuristics || {}).filter(([, v]) => v.detected).map(([k]) => k);
                const isExp = expandedTx === tx.txid;

                return (
                  <React.Fragment key={tx.txid}>
                    <tr className={`tx-row ${isExp ? 'expanded' : ''}`}
                      onClick={() => setExpandedTx(isExp ? null : tx.txid)}>
                      <td style={{ color: 'var(--text-dim)' }}>{idx}</td>
                      <td style={{ fontFamily: 'monospace', fontSize: 12 }}>
                        {truncTxid(tx.txid)}
                      </td>
                      <td>
                        <span className={`badge ${(CLS_COLORS[tx.classification] || {}).cls || 'badge-blue'}`}>
                          {tx.classification}
                        </span>
                      </td>
                      <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                        {tx.input_count != null ? `${tx.input_count} → ${tx.output_count}` : '—'}
                      </td>
                      <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                        {tx.fee_rate_sat_vb != null ? `${tx.fee_rate_sat_vb} sat/vB` : tx.is_coinbase ? 'coinbase' : '—'}
                      </td>
                      <td>
                        {detected.length > 0 ? (
                          detected.slice(0, 3).map(h => (
                            <span key={h} className="badge badge-red" style={{ marginRight: 3, fontSize: 10 }}>{h}</span>
                          ))
                        ) : (
                          <span style={{ color: 'var(--text-dim)', fontSize: 11 }}>none</span>
                        )}
                        {detected.length > 3 && <span style={{ color: 'var(--text-dim)', fontSize: 11 }}>+{detected.length - 3}</span>}
                      </td>
                    </tr>
                    {isExp && (
                      <tr><td colSpan={6} style={{ padding: 0 }}><TxDetail tx={tx} /></td></tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>

        {pageCount > 1 && (
          <div className="pagination">
            <button className="btn" disabled={page === 0} onClick={() => setPage(p => p - 1)}>← Prev</button>
            <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>Page {page + 1} of {pageCount}</span>
            <button className="btn" disabled={page >= pageCount - 1} onClick={() => setPage(p => p + 1)}>Next →</button>
          </div>
        )}
      </div>
    </div>
  );
}
