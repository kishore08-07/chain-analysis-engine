"""
Address Reuse Detection

Detects when the same address appears in both inputs and outputs of a
transaction, or when the same address is used across multiple inputs,
or across multiple transactions within the same block.

Address reuse weakens privacy and links transactions to the same entity.

Uses script_pubkey_hex as a fast proxy for address comparison when
actual addresses are not computed (lean parsing mode).

Reference: Bitcoin Wiki — Address reuse
"""

# Block-level address set, populated by set_block_context() before per-tx apply()
_block_addresses = set()
_block_address_txids = {}  # addr -> set of txids that used it


def set_block_context(transactions):
    """
    Build a block-level address index for cross-transaction reuse detection.
    Called once per block before applying heuristics to each tx.

    Args:
        transactions: list of parsed tx dicts in the block
    """
    global _block_addresses, _block_address_txids
    _block_addresses = set()
    _block_address_txids = {}

    for tx in transactions:
        txid = tx.get('txid', '')
        if tx.get('is_coinbase', False):
            continue

        # Collect all identifiers from this tx
        tx_ids = set()
        for inp in tx.get('vin', []):
            addr = inp.get('address')
            if addr:
                tx_ids.add(addr)
            else:
                prevout = inp.get('prevout')
                if prevout and prevout.get('script_pubkey_hex'):
                    tx_ids.add(prevout['script_pubkey_hex'])

        for out in tx.get('vout', []):
            addr = out.get('address')
            if addr:
                tx_ids.add(addr)
            else:
                spk = out.get('script_pubkey_hex')
                if spk:
                    tx_ids.add(spk)

        for aid in tx_ids:
            _block_addresses.add(aid)
            if aid not in _block_address_txids:
                _block_address_txids[aid] = set()
            _block_address_txids[aid].add(txid)


def apply(tx):
    """
    Detect address reuse within a transaction and across the block.

    Returns:
        dict with 'detected' bool and reuse details
    """
    if tx.get('is_coinbase', False):
        return {'detected': False}

    txid = tx.get('txid', '')

    # Collect input identifiers (address or script_pubkey_hex as fallback)
    input_ids = set()
    input_id_list = []
    for inp in tx.get('vin', []):
        addr = inp.get('address')
        if addr:
            input_ids.add(addr)
            input_id_list.append(addr)
        else:
            prevout = inp.get('prevout')
            if prevout and prevout.get('script_pubkey_hex'):
                spk = prevout['script_pubkey_hex']
                input_ids.add(spk)
                input_id_list.append(spk)

    # Collect output identifiers
    output_ids = set()
    for out in tx.get('vout', []):
        addr = out.get('address')
        if addr:
            output_ids.add(addr)
        else:
            spk = out.get('script_pubkey_hex')
            if spk:
                output_ids.add(spk)

    # Within-transaction: overlap between inputs and outputs
    reused = input_ids & output_ids

    # Within-transaction: duplicate addresses in inputs
    duplicate_inputs = len(input_id_list) != len(set(input_id_list))

    # Cross-transaction: addresses in this tx also used by other txs in same block
    cross_tx_reuse = set()
    all_tx_ids = input_ids | output_ids
    for aid in all_tx_ids:
        other_txids = _block_address_txids.get(aid, set())
        if len(other_txids) > 1 or (len(other_txids) == 1 and txid not in other_txids):
            cross_tx_reuse.add(aid)

    if reused or duplicate_inputs or cross_tx_reuse:
        return {
            'detected': True,
            'reused_addresses': list(reused) if reused else [],
            'input_output_overlap': len(reused),
            'duplicate_input_addresses': duplicate_inputs,
            'cross_tx_reuse_count': len(cross_tx_reuse),
            'confidence': 'high' if reused or duplicate_inputs else 'medium'
        }

    return {'detected': False}
