"""
JSON Output Writer

Produces schema-compliant JSON conforming to the README specification.
Ensures all required fields, types, and constraints are met.

Production features:
  - Per-tx 'signals' array showing all active heuristic detections
  - CIOH suppression annotation when CoinJoin detected
  - Rich heuristic detail fields for each detected heuristic
"""

import json


def build_tx_entry(txid, heuristic_results, classification, **metadata):
    """
    Build a per-transaction entry for the JSON output.

    Args:
        txid: str (64-char hex)
        heuristic_results: dict mapping heuristic_id -> result dict
        classification: str (valid classification label)
        **metadata: optional fields like input_count, output_count, fee_rate_sat_vb

    Returns:
        dict matching the per-transaction schema
    """
    # Only include heuristic IDs and their detected status + relevant fields
    heuristics_out = {}
    for h_id, result in heuristic_results.items():
        entry = {'detected': result.get('detected', False)}

        if result.get('detected'):
            # Include confidence for all detected heuristics
            if 'confidence' in result:
                entry['confidence'] = result['confidence']

            # CIOH suppression annotation
            if result.get('suppressed'):
                entry['suppressed'] = True
                entry['suppressed_by'] = result.get('suppressed_by', '')

            # Heuristic-specific detail fields
            if h_id == 'change_detection':
                for key in ('likely_change_index', 'method'):
                    if key in result:
                        entry[key] = result[key]

            elif h_id == 'coinjoin':
                for key in ('equal_output_count', 'equal_output_value_sats',
                            'input_count', 'distinct_input_types', 'equal_output_ratio'):
                    if key in result:
                        entry[key] = result[key]

            elif h_id == 'consolidation':
                for key in ('input_count', 'output_count', 'types_match', 'io_ratio'):
                    if key in result:
                        entry[key] = result[key]

            elif h_id == 'peeling_chain':
                for key in ('ratio', 'chain_evidence', 'small_output_index', 'large_output_index'):
                    if key in result:
                        entry[key] = result[key]

            elif h_id == 'address_reuse':
                for key in ('input_output_overlap', 'duplicate_input_addresses',
                            'cross_tx_reuse_count'):
                    if key in result:
                        entry[key] = result[key]

            elif h_id == 'self_transfer':
                for key in ('dominant_type', 'output_count', 'address_overlap'):
                    if key in result:
                        entry[key] = result[key]

            elif h_id == 'op_return':
                for key in ('op_return_count', 'outputs'):
                    if key in result:
                        entry[key] = result[key]

            elif h_id == 'round_number_payment':
                for key in ('round_output_count', 'outputs'):
                    if key in result:
                        entry[key] = result[key]

            elif h_id == 'cioh':
                for key in ('input_count', 'unique_addresses'):
                    if key in result:
                        entry[key] = result[key]

        heuristics_out[h_id] = entry

    # Build active signals list — all detected heuristics with suppression state
    signals = []
    for h_id, result in heuristic_results.items():
        if result.get('detected', False):
            sig = {
                'heuristic': h_id,
                'confidence': result.get('confidence', 'medium'),
            }
            if result.get('suppressed'):
                sig['suppressed'] = True
            signals.append(sig)

    tx_entry = {
        'txid': txid,
        'heuristics': heuristics_out,
        'classification': classification,
        'signals': signals,
    }

    # Optional per-tx metadata for web visualization
    for key in ('input_count', 'output_count', 'fee_rate_sat_vb',
                'total_output_value_sats', 'is_coinbase'):
        if key in metadata:
            tx_entry[key] = metadata[key]

    return tx_entry


def build_block_entry(block_hash, block_height, tx_count, analysis_summary,
                      tx_entries=None, timestamp=None):
    """
    Build a per-block entry for the JSON output.

    Args:
        block_hash: str (64-char hex, reversed display)
        block_height: int or None
        tx_count: int
        analysis_summary: dict from stats.compute_block_summary
        tx_entries: list of per-tx entries (optional for blocks after first)
        timestamp: int (unix epoch) from block header, optional

    Returns:
        dict matching the per-block schema
    """
    entry = {
        'block_hash': block_hash,
        'block_height': block_height,
        'tx_count': tx_count,
        'analysis_summary': analysis_summary,
    }

    if timestamp is not None:
        entry['timestamp'] = timestamp

    if tx_entries is not None:
        entry['transactions'] = tx_entries
    else:
        entry['transactions'] = []

    return entry


def build_file_output(blk_filename, block_entries, file_summary):
    """
    Build the complete file-level JSON output.

    Args:
        blk_filename: str (e.g., "blk04330.dat")
        block_entries: list of per-block entries
        file_summary: dict from stats.aggregate_file_summary_with_rates

    Returns:
        dict matching the top-level JSON schema
    """
    return {
        'ok': True,
        'mode': 'chain_analysis',
        'file': blk_filename,
        'block_count': len(block_entries),
        'analysis_summary': file_summary,
        'blocks': block_entries
    }


def write_json(output, filepath):
    """Write the JSON output to a file."""
    with open(filepath, 'w') as f:
        json.dump(output, f, separators=(',', ':'))
