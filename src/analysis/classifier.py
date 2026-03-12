"""
Transaction Classifier

Assigns a classification label to each transaction based on heuristic results.

Classification labels (per README spec):
  - "simple_payment"
  - "consolidation"
  - "coinjoin"
  - "self_transfer"
  - "batch_payment"
  - "unknown"

Uses a priority-based decision tree: most specific classification wins.
"""


def classify(tx, heuristic_results):
    """
    Classify a transaction based on its heuristic results.

    Args:
        tx: parsed transaction dict
        heuristic_results: dict mapping heuristic_id -> result dict

    Returns:
        str: one of the valid classification labels
    """
    if tx.get('is_coinbase', False):
        return 'unknown'

    vout = tx.get('vout', [])
    vin = tx.get('vin', [])

    # Filter spendable outputs
    spendable = [o for o in vout
                 if o.get('script_type', 'unknown') != 'op_return']

    n_inputs = len(vin)
    n_spendable = len(spendable)

    # Priority 1: CoinJoin (most specific, highest priority)
    if heuristic_results.get('coinjoin', {}).get('detected', False):
        return 'coinjoin'

    # Priority 2: Consolidation — many inputs, few outputs
    if heuristic_results.get('consolidation', {}).get('detected', False):
        # Only classify as consolidation if output count is truly small
        # relative to inputs (avoid misclassifying 3-input simple payments)
        cons = heuristic_results['consolidation']
        in_count = cons.get('input_count', n_inputs)
        out_count = cons.get('output_count', n_spendable)
        # Require at least 3:1 ratio or strong type-match signal
        if in_count >= 3 * out_count or cons.get('types_match', False):
            return 'consolidation'

    # Priority 3: Self-transfer — all outputs match input type, no payment signal
    if heuristic_results.get('self_transfer', {}).get('detected', False):
        return 'self_transfer'

    # Priority 4: Batch payment — many outputs (>= 3 spendable)
    # Real batch payments (exchange withdrawals) typically have many outputs
    if n_spendable >= 3:
        return 'batch_payment'

    # Priority 5: Simple payment — 1 or 2 spendable outputs with any input count
    # Wallets routinely select multiple UTXOs to fund a single payment,
    # so there is no upper limit on input count for simple payments.
    if n_spendable >= 1:
        return 'simple_payment'

    return 'unknown'
