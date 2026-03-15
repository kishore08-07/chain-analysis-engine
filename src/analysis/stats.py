"""
Statistics Aggregation

Computes per-block and file-level statistics:
  - Fee rate stats (min, max, median, mean) from non-coinbase transactions
  - Fee rate histogram buckets for distribution shape analysis
  - Privacy score per block (synthetic 0-100 metric)
  - Script type distribution across all outputs
  - Flagged transaction counts
"""

import math


def compute_fee_rate_stats(fee_rates):
    """
    Compute fee rate statistics from a list of fee rates.

    Args:
        fee_rates: list of float (sat/vbyte) from non-coinbase transactions

    Returns:
        dict with min_sat_vb, max_sat_vb, median_sat_vb, mean_sat_vb
    """
    if not fee_rates:
        return {
            'min_sat_vb': 0.0,
            'max_sat_vb': 0.0,
            'median_sat_vb': 0.0,
            'mean_sat_vb': 0.0
        }

    sorted_rates = sorted(fee_rates)
    n = len(sorted_rates)

    min_val = sorted_rates[0]
    max_val = sorted_rates[-1]
    mean_val = sum(sorted_rates) / n

    # Median: middle value (or average of two middles for even count)
    if n % 2 == 1:
        median_val = sorted_rates[n // 2]
    else:
        median_val = (sorted_rates[n // 2 - 1] + sorted_rates[n // 2]) / 2.0

    return {
        'min_sat_vb': round(min_val, 1),
        'max_sat_vb': round(max_val, 1),
        'median_sat_vb': round(median_val, 1),
        'mean_sat_vb': round(mean_val, 1)
    }


def compute_fee_histogram(fee_rates):
    """
    Compute fee rate histogram buckets for distribution shape analysis.

    Buckets: <2, 2-10, 10-50, 50-200, >200 sat/vB
    Returns dict mapping bucket label -> count.
    """
    buckets = {
        '<2': 0,
        '2-10': 0,
        '10-50': 0,
        '50-200': 0,
        '>200': 0,
    }
    for rate in fee_rates:
        if rate < 2:
            buckets['<2'] += 1
        elif rate < 10:
            buckets['2-10'] += 1
        elif rate < 50:
            buckets['10-50'] += 1
        elif rate <= 200:
            buckets['50-200'] += 1
        else:
            buckets['>200'] += 1
    return buckets


def compute_privacy_score(heuristic_detection_counts, classification_distribution,
                          total_transactions):
    """
    Compute a synthetic privacy health score (0-100) for a block.

    Higher score = better privacy practices observed in the block.
    Penalizes address reuse, CIOH, self-transfers.
    Rewards CoinJoin usage, diverse script types.

    Args:
        heuristic_detection_counts: dict of heuristic_id -> count
        classification_distribution: dict of classification -> count
        total_transactions: int

    Returns:
        int 0-100 where 100 = best privacy
    """
    if total_transactions == 0:
        return 100  # Empty block has no privacy issues

    score = 100.0

    # Penalize address reuse (heavy penalty — worst privacy practice)
    addr_reuse = heuristic_detection_counts.get('address_reuse', 0)
    addr_reuse_pct = addr_reuse / total_transactions
    score -= min(addr_reuse_pct * 80, 30)  # Cap at -30 points

    # Penalize high CIOH rate (moderate — it's very common, only penalize extremes)
    cioh_count = heuristic_detection_counts.get('cioh', 0)
    cioh_pct = cioh_count / total_transactions
    if cioh_pct > 0.8:
        score -= 10
    elif cioh_pct > 0.6:
        score -= 5

    # Reward CoinJoin (privacy-enhancing)
    coinjoin_count = classification_distribution.get('coinjoin', 0)
    coinjoin_pct = coinjoin_count / total_transactions
    score += min(coinjoin_pct * 50, 10)  # Bonus up to +10

    # Penalize self-transfers (privacy-neutral but shows wallet pattern)
    self_transfer_pct = classification_distribution.get('self_transfer', 0) / total_transactions
    if self_transfer_pct > 0.3:
        score -= 5

    # Penalize round number payments (makes amount analysis easier)
    round_num = heuristic_detection_counts.get('round_number_payment', 0)
    round_pct = round_num / total_transactions
    score -= min(round_pct * 20, 10)  # Cap at -10

    # Clamp to [0, 100]
    return max(0, min(100, round(score)))


def compute_script_type_distribution(transactions):
    """
    Count script types across all outputs of all transactions.

    Returns:
        dict mapping script_type -> count
    """
    dist = {}
    for tx in transactions:
        for o in tx.get('vout', []):
            stype = o.get('script_type', 'unknown')
            dist[stype] = dist.get(stype, 0) + 1
    return dist


def compute_block_summary(transactions, heuristic_results_list, heuristic_ids,
                          classifications=None):
    """
    Compute analysis summary for a single block.

    Args:
        transactions: list of parsed tx dicts
        heuristic_results_list: list of heuristic result dicts (one per tx)
        heuristic_ids: list of heuristic ID strings
        classifications: optional list of classification strings (one per tx)

    Returns:
        dict with analysis_summary fields
    """
    n_txs = len(transactions)

    # Count flagged
    flagged = 0
    for hr in heuristic_results_list:
        if any(r.get('detected', False) for r in hr.values()):
            flagged += 1

    # Fee rates from non-coinbase txs
    fee_rates = []
    for tx in transactions:
        if not tx.get('is_coinbase', False):
            vbytes = tx.get('vbytes', 0)
            fee = tx.get('fee_sats')  # None = undo unavailable (skip, not zero)
            if vbytes > 0 and fee is not None and fee >= 0:
                fee_rates.append(fee / vbytes)

    # Script distribution
    script_dist = compute_script_type_distribution(transactions)

    # Classification distribution
    class_dist = {}
    if classifications:
        for cls in classifications:
            class_dist[cls] = class_dist.get(cls, 0) + 1

    # Heuristic detection counts
    h_counts = {}
    for hr in heuristic_results_list:
        for h_id, result in hr.items():
            if result.get('detected', False):
                h_counts[h_id] = h_counts.get(h_id, 0) + 1

    # Fee histogram
    fee_histogram = compute_fee_histogram(fee_rates)

    # Privacy score
    privacy_score = compute_privacy_score(h_counts, class_dist, n_txs)

    return {
        'total_transactions_analyzed': n_txs,
        'heuristics_applied': list(heuristic_ids),
        'flagged_transactions': flagged,
        'script_type_distribution': script_dist,
        'fee_rate_stats': compute_fee_rate_stats(fee_rates),
        'fee_rate_histogram': fee_histogram,
        'classification_distribution': class_dist,
        'heuristic_detection_counts': h_counts,
        'privacy_score': privacy_score,
    }


def aggregate_file_summary(block_summaries, heuristic_ids):
    """
    Aggregate per-block summaries into a file-level summary.

    Args:
        block_summaries: list of per-block analysis_summary dicts
        heuristic_ids: list of heuristic ID strings

    Returns:
        dict with file-level analysis_summary
    """
    total_txs = sum(s['total_transactions_analyzed'] for s in block_summaries)
    total_flagged = sum(s['flagged_transactions'] for s in block_summaries)

    # Union of heuristic IDs across blocks
    all_heuristic_ids = set()
    for s in block_summaries:
        all_heuristic_ids.update(s.get('heuristics_applied', []))
    # Ensure canonical order
    ordered_ids = [h_id for h_id in heuristic_ids if h_id in all_heuristic_ids]

    # Aggregate script distribution
    agg_script_dist = {}
    for s in block_summaries:
        for stype, count in s.get('script_type_distribution', {}).items():
            agg_script_dist[stype] = agg_script_dist.get(stype, 0) + count

    # Aggregate classification distribution
    agg_class_dist = {}
    for s in block_summaries:
        for cls, count in s.get('classification_distribution', {}).items():
            agg_class_dist[cls] = agg_class_dist.get(cls, 0) + count

    # Aggregate heuristic detection counts
    agg_h_counts = {}
    for s in block_summaries:
        for h_id, count in s.get('heuristic_detection_counts', {}).items():
            agg_h_counts[h_id] = agg_h_counts.get(h_id, 0) + count

    # Aggregate fee histogram
    agg_fee_hist = {'<2': 0, '2-10': 0, '10-50': 0, '50-200': 0, '>200': 0}
    for s in block_summaries:
        for bucket, count in s.get('fee_rate_histogram', {}).items():
            agg_fee_hist[bucket] = agg_fee_hist.get(bucket, 0) + count

    # Aggregate privacy score (weighted average by tx count)
    weighted_privacy = 0
    for s in block_summaries:
        weighted_privacy += s.get('privacy_score', 100) * s['total_transactions_analyzed']
    avg_privacy = round(weighted_privacy / total_txs) if total_txs > 0 else 100

    return {
        'total_transactions_analyzed': total_txs,
        'heuristics_applied': ordered_ids,
        'flagged_transactions': total_flagged,
        'script_type_distribution': agg_script_dist,
        'fee_rate_stats': None,  # Must be set by caller with all_fee_rates
        'fee_rate_histogram': agg_fee_hist,
        'classification_distribution': agg_class_dist,
        'heuristic_detection_counts': agg_h_counts,
        'privacy_score': avg_privacy,
    }


def aggregate_file_summary_with_rates(block_summaries, heuristic_ids, all_fee_rates):
    """
    Aggregate with accurate file-level fee rate stats computed from raw rates.
    """
    summary = aggregate_file_summary(block_summaries, heuristic_ids)
    summary['fee_rate_stats'] = compute_fee_rate_stats(all_fee_rates)
    # Recompute file-level histogram from raw rates for accuracy
    summary['fee_rate_histogram'] = compute_fee_histogram(all_fee_rates)
    return summary
