"""
Round Number Payment Detection

Identifies outputs with values that are round BTC amounts (e.g., 0.1 BTC,
0.01 BTC, 1 BTC). Round-number outputs are more likely to be payments;
non-round outputs are more likely to be change.

This heuristic complements change detection by flagging the payment side.
"""

# Round denominations in satoshis (minimum 10,000 sats = 0.0001 BTC)
ROUND_AMOUNTS = [
    100_000_000_000,  # 1000 BTC
    10_000_000_000,   # 100 BTC
    1_000_000_000,    # 10 BTC
    500_000_000,      # 5 BTC
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


def _is_round(value_sats):
    """Check if a satoshi value is a round BTC denomination."""
    if value_sats <= 0:
        return False
    for r in ROUND_AMOUNTS:
        if value_sats % r == 0:
            return True
    return False


def _get_denomination(value_sats):
    """Get the largest round denomination a value is divisible by."""
    for r in ROUND_AMOUNTS:
        if value_sats % r == 0:
            return r
    return None


def apply(tx):
    """
    Detect round number payment outputs.

    Returns:
        dict with 'detected' bool and round output details
    """
    if tx.get('is_coinbase', False):
        return {'detected': False}

    vout = tx.get('vout', [])
    round_outputs = []

    for i, o in enumerate(vout):
        if o.get('script_type') == 'op_return':
            continue
        val = o.get('value_sats', 0)
        if _is_round(val):
            denom = _get_denomination(val)
            round_outputs.append({
                'index': i,
                'value_sats': val,
                'denomination_sats': denom,
                'btc_value': val / 100_000_000
            })

    if round_outputs:
        return {
            'detected': True,
            'round_output_count': len(round_outputs),
            'outputs': round_outputs,
            'confidence': 'medium'
        }

    return {'detected': False}
