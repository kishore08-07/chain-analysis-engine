"""
JSON Output Writer

Produces schema-compliant JSON conforming to the README specification.
Ensures all required fields, types, and constraints are met.
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
        # Include extra fields for change_detection
        if h_id == 'change_detection' and result.get('detected'):
            if 'likely_change_index' in result:
                entry['likely_change_index'] = result['likely_change_index']
            if 'method' in result:
                entry['method'] = result['method']
            if 'confidence' in result:
                entry['confidence'] = result['confidence']
        # Include confidence for any detected heuristic
        if result.get('detected') and 'confidence' in result and h_id != 'change_detection':
            entry['confidence'] = result['confidence']
        heuristics_out[h_id] = entry

    tx_entry = {
        'txid': txid,
        'heuristics': heuristics_out,
        'classification': classification
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
        block_height: int
        tx_count: int
        analysis_summary: dict from stats.compute_block_summary
        tx_entries: list of per-tx entries (optional for blocks after first)
        timestamp: int (unix epoch) from block header, optional

    Returns:
        dict matching the per-block schema
    """
    entry = {
        'block_hash': block_hash,
        'block_height': block_height if block_height is not None else 0,
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
        json.dump(output, f, indent=2)
