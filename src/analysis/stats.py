"""
Statistics Aggregation

Computes per-block and file-level statistics:
  - Fee rate stats (min, max, median, mean) from non-coinbase transactions
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
            fee = tx.get('fee_sats', 0)
            if vbytes > 0:
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

    return {
        'total_transactions_analyzed': n_txs,
        'heuristics_applied': list(heuristic_ids),
        'flagged_transactions': flagged,
        'script_type_distribution': script_dist,
        'fee_rate_stats': compute_fee_rate_stats(fee_rates),
        'classification_distribution': class_dist,
        'heuristic_detection_counts': h_counts,
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

    # Aggregate fee rates — we need the raw rates across all blocks
    # so we store them during block processing
    # For now, recompute from the block stats (min of mins, max of maxes)
    # This is NOT correct for median — median must be over all txs
    # We'll pass raw fee rates from caller instead

    return {
        'total_transactions_analyzed': total_txs,
        'heuristics_applied': ordered_ids,
        'flagged_transactions': total_flagged,
        'script_type_distribution': agg_script_dist,
        'fee_rate_stats': None,  # Must be set by caller with all_fee_rates
        'classification_distribution': agg_class_dist,
        'heuristic_detection_counts': agg_h_counts,
    }


def aggregate_file_summary_with_rates(block_summaries, heuristic_ids, all_fee_rates):
    """
    Aggregate with accurate file-level fee rate stats computed from raw rates.
    """
    summary = aggregate_file_summary(block_summaries, heuristic_ids)
    summary['fee_rate_stats'] = compute_fee_rate_stats(all_fee_rates)
    return summary
