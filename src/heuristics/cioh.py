"""
Common Input Ownership Heuristic (CIOH)

Foundational chain analysis assumption: if multiple inputs are spent
together in a single transaction, they are probably controlled by
the same wallet / entity.

Reference: Meiklejohn et al., "A Fistful of Bitcoins" (2013)
"""


def apply(tx):
    """
    Apply CIOH to a parsed transaction.

    Args:
        tx: dict from block_parser with 'vin', 'is_coinbase' fields

    Returns:
        dict with 'detected' bool and metadata
    """
    if tx.get('is_coinbase', False):
        return {'detected': False}

    vin = tx.get('vin', [])
    n_inputs = len(vin)

    if n_inputs <= 1:
        return {'detected': False}

    # Collect unique input identifiers.
    # Priority: address -> prevout script_pubkey_hex -> outpoint (txid:vout).
    # Outpoint fallback is weaker than address/script identity but avoids
    # systematic undercount in lean mode when prevouts are unavailable.
    input_ids = set()
    used_outpoint_fallback = False
    for inp in vin:
        addr = inp.get('address')
        if addr:
            input_ids.add(addr)
            continue

        prevout = inp.get('prevout')
        if prevout and prevout.get('script_pubkey_hex'):
            input_ids.add(prevout['script_pubkey_hex'])
            continue

        prev_txid = inp.get('txid')
        prev_vout = inp.get('vout')
        if prev_txid is not None and prev_vout is not None:
            input_ids.add(f"{prev_txid}:{prev_vout}")
            used_outpoint_fallback = True

    result = {
        'detected': True,
        'input_count': n_inputs,
        'unique_addresses': len(input_ids),
        'confidence': 'high' if n_inputs >= 3 else 'medium'
    }

    if used_outpoint_fallback:
        result['approximate_identifiers'] = True

    return result
