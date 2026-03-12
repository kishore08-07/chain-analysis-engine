"""
Peeling Chain Detection

Detects peeling chain patterns: a large input is split into one small
output (payment) and one large output (change), with a significant
value asymmetry between the two outputs.

This is a common pattern in exchange withdrawals and automated wallets
that "peel off" small payments from a large UTXO.

Detection criteria:
  - Few inputs (1-3)
  - Exactly 2 spendable outputs
  - One output is significantly larger than the other (ratio > 10:1)
  - Optionally tracks spend chains within the same block
"""

# Block-level spend graph for chain tracking
_block_spend_graph = {}  # txid -> set of output txids that spend this tx's outputs


def set_block_context(transactions):
    """
    Build a block-level spend graph for chain tracking within the block.
    Called once per block before applying heuristics.
    """
    global _block_spend_graph
    _block_spend_graph = {}

    # Build map: txid -> tx for quick lookup
    txid_set = set()
    for tx in transactions:
        txid_set.add(tx.get('txid', ''))

    # Build spending relationships within the block
    for tx in transactions:
        if tx.get('is_coinbase', False):
            continue
        txid = tx.get('txid', '')
        for inp in tx.get('vin', []):
            prev_txid = inp.get('txid')
            if prev_txid and prev_txid in txid_set:
                if prev_txid not in _block_spend_graph:
                    _block_spend_graph[prev_txid] = set()
                _block_spend_graph[prev_txid].add(txid)


def apply(tx):
    """
    Detect peeling chain patterns.

    Returns:
        dict with 'detected' bool and peeling metrics
    """
    if tx.get('is_coinbase', False):
        return {'detected': False}

    vin = tx.get('vin', [])
    vout = tx.get('vout', [])

    # Peeling chains typically have few inputs (1-3)
    if len(vin) > 3:
        return {'detected': False}

    # Filter spendable outputs
    spendable = [o for o in vout
                 if o.get('script_type', 'unknown') != 'op_return'
                 and o.get('value_sats', 0) > 0]

    if len(spendable) != 2:
        return {'detected': False}

    val_a = spendable[0].get('value_sats', 0)
    val_b = spendable[1].get('value_sats', 0)

    if val_a == 0 or val_b == 0:
        return {'detected': False}

    # Check value asymmetry
    larger = max(val_a, val_b)
    smaller = min(val_a, val_b)

    ratio = larger / smaller if smaller > 0 else 0

    if ratio >= 10:
        small_idx = 0 if val_a < val_b else 1
        large_idx = 1 - small_idx

        # Check if this tx's output is spent again in the same block (chain evidence)
        txid = tx.get('txid', '')
        has_chain_successor = txid in _block_spend_graph
        
        # Check if any input comes from another peeling-like tx in this block
        has_chain_predecessor = False
        for inp in vin:
            prev_txid = inp.get('txid')
            if prev_txid and prev_txid in _block_spend_graph:
                has_chain_predecessor = True
                break

        chain_evidence = has_chain_successor or has_chain_predecessor

        if ratio >= 50:
            confidence = 'high'
        elif chain_evidence:
            confidence = 'high'
        else:
            confidence = 'medium'

        return {
            'detected': True,
            'small_output_index': small_idx,
            'large_output_index': large_idx,
            'ratio': round(ratio, 1),
            'chain_evidence': chain_evidence,
            'confidence': confidence
        }

    return {'detected': False}
