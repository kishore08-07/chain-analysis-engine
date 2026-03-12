"""
CoinJoin Detection

Identifies CoinJoin transactions: multiple inputs from apparently different
owners, with equal-value outputs designed to obscure the transaction graph.

Detection criteria:
  - Multiple inputs (>= 3)
  - Multiple equal-value outputs (>= 3 outputs sharing the same satoshi value)
  - High input-to-equal-output ratio
  - Equal outputs represent a significant fraction of all spendable outputs

Reference: Maxwell, "CoinJoin: Bitcoin privacy for the real world" (2013)
"""


def apply(tx):
    """
    Detect CoinJoin patterns.

    Returns:
        dict with 'detected' bool and coinjoin metrics
    """
    if tx.get('is_coinbase', False):
        return {'detected': False}

    vin = tx.get('vin', [])
    vout = tx.get('vout', [])
    n_inputs = len(vin)

    # Filter to spendable outputs (exclude OP_RETURN, zero-value)
    spendable = [o for o in vout
                 if o.get('script_type', 'unknown') != 'op_return'
                 and o.get('value_sats', 0) > 0]

    if n_inputs < 3 or len(spendable) < 3:
        return {'detected': False}

    # Count output value frequencies
    value_counts = {}
    for o in spendable:
        v = o.get('value_sats', 0)
        value_counts[v] = value_counts.get(v, 0) + 1

    # Find the most common equal-value output
    if not value_counts:
        return {'detected': False}

    max_equal_value = max(value_counts, key=value_counts.get)
    max_equal_count = value_counts[max_equal_value]

    # CoinJoin: at least 3 equal-value outputs
    if max_equal_count >= 3:
        # False positive filter: equal outputs should be a meaningful fraction
        # of total outputs (not just 3 dust outputs in a batch payment)
        equal_ratio = max_equal_count / len(spendable)

        # Filter: if equal outputs are very small relative to total output value,
        # it's likely not CoinJoin but batch payment with coincidental equal amounts
        total_output_value = sum(o.get('value_sats', 0) for o in spendable)
        equal_total_value = max_equal_value * max_equal_count
        value_ratio = equal_total_value / total_output_value if total_output_value > 0 else 0

        # Reject if equal outputs are negligible (< 10% of total value)
        # AND they're a small fraction of outputs
        if value_ratio < 0.1 and equal_ratio < 0.3:
            return {'detected': False}

        # Check diverse input script types (different participants)
        input_types = set()
        for inp in vin:
            stype = inp.get('script_type', 'unknown')
            if stype not in ('unknown', 'coinbase'):
                input_types.add(stype)

        # Strong CoinJoin signal: many equal outputs, many inputs, significant value
        if max_equal_count >= 5 and n_inputs >= 5:
            confidence = 'high'
        elif equal_ratio >= 0.5 and n_inputs >= max_equal_count:
            confidence = 'high'
        else:
            confidence = 'medium'

        return {
            'detected': True,
            'equal_output_count': max_equal_count,
            'equal_output_value_sats': max_equal_value,
            'input_count': n_inputs,
            'distinct_input_types': len(input_types),
            'equal_output_ratio': round(equal_ratio, 2),
            'confidence': confidence
        }

    return {'detected': False}
