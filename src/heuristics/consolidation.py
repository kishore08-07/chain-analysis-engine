"""
Consolidation Detection

Detects consolidation transactions: many inputs combined into 1–2 outputs,
typically of the same script type. These are common wallet maintenance
operations that reduce UTXO set size.

Detection criteria:
  - At least 3 inputs
  - At most 2 spendable outputs
  - Outputs typically match input script types
  - High input-to-output ratio
"""


def apply(tx):
    """
    Detect consolidation patterns.

    Returns:
        dict with 'detected' bool and consolidation metrics
    """
    if tx.get('is_coinbase', False):
        return {'detected': False}

    vin = tx.get('vin', [])
    vout = tx.get('vout', [])
    n_inputs = len(vin)

    # Filter to spendable outputs
    spendable = [o for o in vout
                 if o.get('script_type', 'unknown') != 'op_return']

    n_spendable = len(spendable)

    if n_inputs < 3 or n_spendable > 2:
        return {'detected': False}

    # Check if outputs match input script types
    input_types = set()
    input_type_counts = {}
    for inp in vin:
        stype = inp.get('script_type', 'unknown')
        if stype not in ('unknown', 'coinbase'):
            input_types.add(stype)
            input_type_counts[stype] = input_type_counts.get(stype, 0) + 1

    output_types = set()
    for o in spendable:
        stype = o.get('script_type', 'unknown')
        if stype != 'unknown':
            output_types.add(stype)

    types_match = output_types.issubset(input_types) if output_types else False

    # Input-to-output ratio indicates strength of consolidation
    io_ratio = n_inputs / n_spendable if n_spendable > 0 else n_inputs

    # High confidence: many inputs, single output, types match
    if n_inputs >= 5 and n_spendable == 1 and types_match:
        confidence = 'high'
    elif n_inputs >= 10:
        confidence = 'high'  # Very many inputs is strong consolidation signal
    elif types_match and io_ratio >= 3:
        confidence = 'medium'
    else:
        confidence = 'medium'

    return {
        'detected': True,
        'input_count': n_inputs,
        'output_count': n_spendable,
        'types_match': types_match,
        'io_ratio': round(io_ratio, 1),
        'confidence': confidence
    }
