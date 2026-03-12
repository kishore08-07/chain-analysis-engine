"""
Sherlock — Bitcoin Chain Analysis Engine

Main entry point. Orchestrates:
  1. Parse block file (blk*.dat) and undo file (rev*.dat) using XOR key
  2. Apply chain analysis heuristics to every transaction
  3. Classify each transaction
  4. Compute per-block and file-level statistics
  5. Write JSON and Markdown output to out/

Usage:
    python3 src/main.py --block <blk.dat> <rev.dat> <xor.dat>
"""

import sys
import os
import json

# Ensure project root is on path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.block_parser import parse_blocks_from_file
from src.core.undo_parser import parse_undo_file
from src.heuristics.engine import apply_all, is_flagged, ALL_HEURISTIC_IDS, set_block_context
from src.analysis.classifier import classify
from src.analysis.stats import (
    compute_block_summary,
    aggregate_file_summary_with_rates,
    compute_fee_rate_stats,
)
from src.output.json_writer import (
    build_tx_entry,
    build_block_entry,
    build_file_output,
    write_json,
)
from src.output.md_writer import generate_report, write_markdown


def error_exit(code, message):
    """Print structured error JSON to stdout and exit 1."""
    error = {
        "ok": False,
        "error": {
            "code": code,
            "message": message
        }
    }
    print(json.dumps(error))
    sys.exit(1)


def process_block_file(blk_file, rev_file, xor_file):
    """
    Full chain analysis pipeline for a single block file.

    Returns:
        dict: complete file-level JSON output
    """
    # --- Step 1: Parse undo data ---
    undo_data = None
    try:
        undo_data = parse_undo_file(rev_file, xor_file)
    except Exception:
        # Non-fatal: proceed without undo data (fees will be 0)
        undo_data = None

    # --- Step 2: Parse blocks ---
    try:
        blocks, has_errors = parse_blocks_from_file(
            blk_file, undo_data, network='mainnet', xor_file_path=xor_file,
            full_tx_block_indices={0}  # Only block[0] needs full detail for JSON
        )
    except Exception as e:
        error_exit("BLOCK_PARSE_ERROR", f"Failed to parse block file: {e}")

    if not blocks:
        error_exit("NO_BLOCKS", "No blocks found in file")

    # --- Step 3: Process each block ---
    blk_basename = os.path.basename(blk_file)
    block_entries = []
    block_summaries = []
    all_fee_rates = []  # Collect across all blocks for file-level stats

    for block_idx, block in enumerate(blocks):
        if not block.get('ok', False):
            # Skip errored blocks
            continue

        header = block.get('block_header', {})
        block_hash = header.get('block_hash', '0' * 64)
        block_height = block.get('coinbase', {}).get('bip34_height')
        block_timestamp = header.get('timestamp')
        transactions = block.get('transactions', [])
        tx_count = block.get('tx_count', len(transactions))

        # Set block-level context for cross-transaction heuristics
        set_block_context(transactions)

        # Apply heuristics and classify each transaction
        tx_entries = []
        heuristic_results_list = []
        classifications = []
        block_fee_rates = []

        for tx in transactions:
            # Apply all heuristics
            h_results = apply_all(tx)
            heuristic_results_list.append(h_results)

            # Classify
            classification = classify(tx, h_results)
            classifications.append(classification)

            # Build tx entry (with metadata for block[0])
            txid = tx.get('txid', '0' * 64)
            tx_metadata = {}
            if block_idx == 0:
                tx_metadata['input_count'] = len(tx.get('vin', []))
                tx_metadata['output_count'] = len(tx.get('vout', []))
                tx_metadata['is_coinbase'] = tx.get('is_coinbase', False)
                if not tx.get('is_coinbase', False):
                    vbytes = tx.get('vbytes', 0)
                    fee = tx.get('fee_sats', 0)
                    if vbytes > 0:
                        tx_metadata['fee_rate_sat_vb'] = round(fee / vbytes, 2)
                total_out = sum(o.get('value_sats', 0) for o in tx.get('vout', []))
                tx_metadata['total_output_value_sats'] = total_out

            tx_entry = build_tx_entry(txid, h_results, classification, **tx_metadata)
            tx_entries.append(tx_entry)

            # Collect fee rate for stats (non-coinbase only)
            if not tx.get('is_coinbase', False):
                vbytes = tx.get('vbytes', 0)
                fee = tx.get('fee_sats', 0)
                if vbytes > 0:
                    rate = fee / vbytes
                    block_fee_rates.append(rate)
                    all_fee_rates.append(rate)

        # Compute block summary
        block_summary = compute_block_summary(
            transactions, heuristic_results_list, ALL_HEURISTIC_IDS,
            classifications
        )

        block_summaries.append(block_summary)

        # For blocks[0], include full transaction array
        # For subsequent blocks, omit to reduce JSON size and write time
        block_entry = build_block_entry(
            block_hash=block_hash,
            block_height=block_height,
            tx_count=tx_count,
            analysis_summary=block_summary,
            tx_entries=tx_entries if block_idx == 0 else None,
            timestamp=block_timestamp,
        )
        block_entries.append(block_entry)

    if not block_entries:
        error_exit("NO_VALID_BLOCKS", "No valid blocks parsed from file")

    # --- Step 4: Compute file-level summary ---
    file_summary = aggregate_file_summary_with_rates(
        block_summaries, ALL_HEURISTIC_IDS, all_fee_rates
    )

    # --- Step 5: Build output ---
    file_output = build_file_output(blk_basename, block_entries, file_summary)

    return file_output


def main():
    # Parse arguments
    if len(sys.argv) < 2 or sys.argv[1] != '--block':
        error_exit("INVALID_ARGS",
                    "Usage: python3 src/main.py --block <blk.dat> <rev.dat> <xor.dat>")

    if len(sys.argv) < 5:
        error_exit("INVALID_ARGS",
                    "Block mode requires: --block <blk.dat> <rev.dat> <xor.dat>")

    blk_file = sys.argv[2]
    rev_file = sys.argv[3]
    xor_file = sys.argv[4]

    # Validate files
    for fpath in [blk_file, rev_file, xor_file]:
        if not os.path.isfile(fpath):
            error_exit("FILE_NOT_FOUND", f"File not found: {fpath}")

    # Create output directory
    os.makedirs('out', exist_ok=True)

    # Derive output filenames from blk filename
    blk_basename = os.path.basename(blk_file)
    blk_stem = os.path.splitext(blk_basename)[0]  # e.g., "blk04330"

    json_path = os.path.join('out', f'{blk_stem}.json')
    md_path = os.path.join('out', f'{blk_stem}.md')

    # Run analysis
    try:
        file_output = process_block_file(blk_file, rev_file, xor_file)
    except SystemExit:
        raise
    except Exception as e:
        error_exit("ANALYSIS_ERROR", str(e))

    # Write JSON
    try:
        write_json(file_output, json_path)
    except Exception as e:
        error_exit("IO_ERROR", f"Failed to write JSON: {e}")

    # Generate and write Markdown
    try:
        md_content = generate_report(file_output)
        write_markdown(md_content, md_path)
    except Exception as e:
        error_exit("IO_ERROR", f"Failed to write Markdown: {e}")

    sys.exit(0)


if __name__ == '__main__':
    main()
