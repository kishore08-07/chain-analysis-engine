"""
Self-Transfer Detection

Identifies transactions where all inputs and outputs appear to belong
to the same entity. All outputs match the input script type pattern,
and the transaction has no obvious "payment" component.

Detection criteria:
  - All spendable outputs use the same script type as the dominant input type
  - No round-number outputs (suggesting no external payment)
  - Typically 1–2 outputs
  - All input addresses (if available) are distinct from output addresses
    (true self-transfer re-uses types but not necessarily same addresses)
"""

ROUND_AMOUNTS = [
    100_000_000,  # 1 BTC
    50_000_000,
    10_000_000,
    5_000_000,
    1_000_000,
    500_000,
    100_000,
    50_000,
    10_000,
]


def _is_round(value_sats):
    if value_sats <= 0:
        return False
    for r in ROUND_AMOUNTS:
        if value_sats % r == 0:
            return True
    return False


def apply(tx):
    """
    Detect self-transfer patterns.

    Returns:
        dict with 'detected' bool and metadata
    """
    if tx.get('is_coinbase', False):
        return {'detected': False}

    vin = tx.get('vin', [])
    vout = tx.get('vout', [])

    if len(vin) == 0:
        return {'detected': False}

    # Filter to spendable outputs
    spendable = [o for o in vout
                 if o.get('script_type', 'unknown') != 'op_return']

    if not spendable or len(spendable) > 2:
        return {'detected': False}

    # Get dominant input script type
    input_type_counts = {}
    for inp in vin:
        stype = inp.get('script_type', 'unknown')
        if stype not in ('unknown', 'coinbase'):
            input_type_counts[stype] = input_type_counts.get(stype, 0) + 1

    if not input_type_counts:
        return {'detected': False}

    dominant_type = max(input_type_counts, key=input_type_counts.get)
    total_typed_inputs = sum(input_type_counts.values())

    # All inputs should be predominantly the same type for self-transfer
    dominant_ratio = input_type_counts[dominant_type] / total_typed_inputs
    if dominant_ratio < 0.8:
        return {'detected': False}

    # All spendable outputs must match dominant input type
    all_match = all(o.get('script_type') == dominant_type for o in spendable)
    if not all_match:
        return {'detected': False}

    # No round-number outputs (which would suggest a payment)
    has_round = any(_is_round(o.get('value_sats', 0)) for o in spendable)
    if has_round:
        return {'detected': False}

    # Additional check: if we have addresses, check for input-output address overlap
    # (self-transfer often sends to a new address of the same type)
    input_addrs = set()
    for inp in vin:
        addr = inp.get('address')
        if addr:
            input_addrs.add(addr)

    output_addrs = set()
    for o in spendable:
        addr = o.get('address')
        if addr:
            output_addrs.add(addr)

    # If addresses are available and there's overlap, it's a stronger signal
    addr_overlap = bool(input_addrs and output_addrs and (input_addrs & output_addrs))

    confidence = 'medium'
    if addr_overlap:
        confidence = 'high'  # Address reuse in self-transfer is very strong signal
    elif len(vin) >= 2 and len(spendable) == 1:
        confidence = 'high'  # Multiple inputs to single same-type output = likely consolidation/self-transfer

    return {
        'detected': True,
        'dominant_type': dominant_type,
        'output_count': len(spendable),
        'address_overlap': addr_overlap,
        'confidence': confidence
    }
