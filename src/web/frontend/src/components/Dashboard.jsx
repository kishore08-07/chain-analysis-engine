import React from 'react';
import { fmtNum } from '../utils/format';
import { CLS_COLORS } from '../constants/colors';
import { TT } from '../constants/tooltips';
import Tooltip from './ui/Tooltip';
import StatBox from './ui/StatBox';
import DonutChart from './charts/DonutChart';
import HeuristicBars from './charts/HeuristicBars';
import ScriptTypeBar from './charts/ScriptTypeBar';
import FeeRateViz from './charts/FeeRateViz';

export default function Dashboard({ data }) {
  const summary = data.analysis_summary || {};
  const feeStats = summary.fee_rate_stats || {};
  const scriptDist = summary.script_type_distribution || {};
  const classDist = summary.classification_distribution || {};
  const hCounts = summary.heuristic_detection_counts || {};
  const totalTxs = summary.total_transactions_analyzed || 0;
  const privacyScore = summary.privacy_score ?? null;

  return (
    <div>
      {/* Key stats */}
      <div className="card">
        <h2 className="section-title">
          📊 Analysis Overview — <span style={{ color: 'var(--accent)' }}>{data.file}</span>
          <Tooltip text={TT.file} />
        </h2>
        <p className="section-subtitle">
          A high-level picture of everything we found across all blocks in this file.
          Every metric below is aggregated from <strong>{fmtNum(totalTxs)}</strong> transactions.
        </p>
        <div style={{ marginTop: 16 }} className="stat-grid">
          <StatBox value={data.block_count} label="Blocks" tip={TT.blocks} />
          <StatBox value={fmtNum(totalTxs)} label="Transactions" raw tip={TT.transactions} />
          <StatBox value={fmtNum(summary.flagged_transactions || 0)} label="Flagged" color="var(--red)" raw tip={TT.flagged} />
          <StatBox value={(summary.heuristics_applied || []).length} label="Heuristics Run" tip={TT.heuristics} />
          <StatBox value={`${feeStats.median_sat_vb ?? '—'} sat/vB`} label="Median Fee Rate" raw tip={TT.medianFee} />
          <StatBox value={`${feeStats.min_sat_vb ?? '—'} — ${feeStats.max_sat_vb ?? '—'}`} label="Fee Rate Range" raw tip={TT.feeRange} />
          {privacyScore !== null && (
            <StatBox
              value={privacyScore}
              label="Privacy Score"
              color={privacyScore >= 70 ? 'var(--green)' : privacyScore >= 40 ? 'var(--orange)' : 'var(--red)'}
              tip={TT.privacyScore}
            />
          )}
        </div>
      </div>

      {/* Two-column: Classification donut + Heuristics bars */}
      <div className="dash-grid">
        <div className="card">
          <h3 className="card-subtitle">
            What kind of transactions are these?
            <Tooltip text="We labelled every transaction using pattern recognition — like sorting mail into categories." />
          </h3>
          <DonutChart data={classDist} colorMap={CLS_COLORS} total={totalTxs} />
        </div>
        <div className="card">
          <h3 className="card-subtitle">
            Which detective rules fired?
            <Tooltip text="Each bar shows how many transactions triggered that particular detection rule. Hover a bar label for details." />
          </h3>
          <HeuristicBars counts={hCounts} total={totalTxs} heuristics={summary.heuristics_applied || []} />
        </div>
      </div>

      {/* Two-column: Script types + Fee rates */}
      <div className="dash-grid">
        <div className="card">
          <h3 className="card-subtitle">
            What locking formats were used?
            <Tooltip text="Each output has a 'script type' — the type of cryptographic lock placed on the coins. Newer formats are more private and efficient." />
          </h3>
          <ScriptTypeBar dist={scriptDist} />
        </div>
        <div className="card">
          <h3 className="card-subtitle">
            How much did senders pay in fees?
            <Tooltip text="Miners choose which transactions to include based on fee rate. Higher fee = faster confirmation." />
          </h3>
          <FeeRateViz stats={feeStats} />
        </div>
      </div>
    </div>
  );
}
