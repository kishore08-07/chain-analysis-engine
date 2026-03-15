"""
Change Detection Heuristic

Identifies the likely change output in a transaction using multiple
detection methods:
  1. Script type match — change output matches dominant input script type
  2. Round number — payment amounts tend to be round; non-round is likely change
  3. Output ordering — change is often at index 0 or last
  4. Value analysis — the smaller non-dust output is likely change in simple payments

Reference: Nick, "Data-Driven De-Anonymization in Bitcoin" (2015)
"""

# Round BTC denominations in satoshis
ROUND_AMOUNTS = [
    100_000_000_000,  # 1000 BTC
    10_000_000_000,   # 100 BTC
    1_000_000_000,    # 10 BTC
    100_000_000,      # 1 BTC
    50_000_000,       # 0.5 BTC
    10_000_000,       # 0.1 BTC
    5_000_000,        # 0.05 BTC
    1_000_000,        # 0.01 BTC
    500_000,          # 0.005 BTC
    100_000,          # 0.001 BTC
    50_000,           # 0.0005 BTC
    10_000,           # 0.0001 BTC
]


def _is_round_amount(value_sats):
    """Check if a value is a round BTC denomination."""
    if value_sats <= 0:
        return False
    for r in ROUND_AMOUNTS:
        if value_sats % r == 0:
            return True
    return False


def _get_dominant_input_script_type(tx):
    """Get the most common script type among inputs."""
    type_counts = {}
    for inp in tx.get('vin', []):
        stype = inp.get('script_type', 'unknown')
        if stype not in ('unknown', 'coinbase'):
            type_counts[stype] = type_counts.get(stype, 0) + 1
    if not type_counts:
        return None
    return max(type_counts, key=type_counts.get)


def apply(tx):
    """
    Apply change detection heuristic.

    Returns:
        dict with 'detected', 'likely_change_index', 'method', 'confidence'
    """
    if tx.get('is_coinbase', False):
        return {'detected': False}

    vout = tx.get('vout', [])

    # Filter to spendable outputs (exclude OP_RETURN)
    spendable = [(i, o) for i, o in enumerate(vout)
                 if o.get('script_type', 'unknown') != 'op_return']

    if len(spendable) < 2:
        return {'detected': False}

    dominant_input_type = _get_dominant_input_script_type(tx)

    # Method 1: Script type match
    if dominant_input_type:
        matching = [(i, o) for i, o in spendable
                    if o.get('script_type') == dominant_input_type]
        non_matching = [(i, o) for i, o in spendable
                        if o.get('script_type') != dominant_input_type]

        if len(matching) == 1 and len(non_matching) >= 1:
            return {
                'detected': True,
                'likely_change_index': matching[0][0],
                'method': 'script_type_match',
                'confidence': 'high'
            }

    # Method 2: Round number analysis
    round_outputs = [(i, o) for i, o in spendable
                     if _is_round_amount(o.get('value_sats', 0))]
    non_round_outputs = [(i, o) for i, o in spendable
                         if not _is_round_amount(o.get('value_sats', 0))]

    if len(round_outputs) >= 1 and len(non_round_outputs) == 1:
        return {
            'detected': True,
            'likely_change_index': non_round_outputs[0][0],
            'method': 'round_number',
            'confidence': 'medium'
        }

    # Method 3: Value analysis — in 2-output tx, larger output is likely change
    # (payment is usually the smaller amount, change returns the rest)
    if len(spendable) == 2:
        idx_a, out_a = spendable[0]
        idx_b, out_b = spendable[1]
        val_a = out_a.get('value_sats', 0)
        val_b = out_b.get('value_sats', 0)

        if val_a != val_b:
            # Larger output is likely change (common in peeling patterns)
            if val_a > val_b:
                change_idx = idx_a
            else:
                change_idx = idx_b
            return {
                'detected': True,
                'likely_change_index': change_idx,
                'method': 'value_analysis',
                'confidence': 'low'
            }

    return {'detected': False}
