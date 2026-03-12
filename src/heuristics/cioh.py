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

    # Collect unique addresses from inputs
    addresses = set()
    for inp in vin:
        addr = inp.get('address')
        if addr:
            addresses.add(addr)

    return {
        'detected': True,
        'input_count': n_inputs,
        'unique_addresses': len(addresses),
        'confidence': 'high' if n_inputs >= 3 else 'medium'
    }
