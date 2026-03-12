"""
Heuristic Engine

Orchestrates the application of all chain analysis heuristics to a transaction.
Each heuristic is a pure function: heuristic(tx) -> result dict with 'detected' bool.
Some heuristics support block-level context for cross-transaction analysis.
"""

from . import (
    cioh,
    change_detection,
    address_reuse,
    coinjoin,
    consolidation,
    self_transfer,
    peeling_chain,
    op_return,
    round_number,
)

# Canonical ordering of heuristic IDs — deterministic across runs
HEURISTIC_REGISTRY = [
    ('cioh', cioh),
    ('change_detection', change_detection),
    ('address_reuse', address_reuse),
    ('coinjoin', coinjoin),
    ('consolidation', consolidation),
    ('self_transfer', self_transfer),
    ('peeling_chain', peeling_chain),
    ('op_return', op_return),
    ('round_number_payment', round_number),
]

# List of all heuristic IDs in canonical order
ALL_HEURISTIC_IDS = [h_id for h_id, _ in HEURISTIC_REGISTRY]


def set_block_context(transactions):
    """
    Set block-level context for heuristics that need cross-transaction info.
    Must be called once per block before calling apply_all() on each tx.

    Args:
        transactions: list of all parsed tx dicts in the block
    """
    # Address reuse needs to see all addresses in the block
    if hasattr(address_reuse, 'set_block_context'):
        address_reuse.set_block_context(transactions)

    # Peeling chain needs spend graph for chain tracking
    if hasattr(peeling_chain, 'set_block_context'):
        peeling_chain.set_block_context(transactions)


def apply_all(tx):
    """
    Apply all registered heuristics to a transaction.

    Args:
        tx: dict from block_parser (parse_block_tx_full or parse_coinbase_tx_full)

    Returns:
        dict mapping heuristic_id -> result dict (each has 'detected' bool)
    """
    results = {}
    for h_id, h_module in HEURISTIC_REGISTRY:
        try:
            results[h_id] = h_module.apply(tx)
        except Exception:
            # Robust: never crash on a single heuristic failure
            results[h_id] = {'detected': False}
    return results


def is_flagged(heuristic_results):
    """
    Check if a transaction has at least one heuristic with detected=True.
    """
    return any(r.get('detected', False) for r in heuristic_results.values())
