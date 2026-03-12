"""
OP_RETURN Analysis

Detects OP_RETURN outputs and classifies the embedded data by protocol.
Tracks usage patterns within the block.

Known protocols:
  - Omni Layer: prefix 'omni' (0x6f6d6e69)
  - OpenTimestamps: prefix 0x0109f91102
  - Counterparty: prefix 'CNTRPRTY'
  - Stacks (STX): various markers

Reference: https://en.bitcoin.it/wiki/OP_RETURN
"""


def apply(tx):
    """
    Detect and classify OP_RETURN outputs.

    Returns:
        dict with 'detected' bool and protocol classification
    """
    if tx.get('is_coinbase', False):
        return {'detected': False}

    vout = tx.get('vout', [])
    op_return_outputs = []

    for i, o in enumerate(vout):
        if o.get('script_type') == 'op_return':
            data_hex = o.get('op_return_data_hex', '')
            protocol = o.get('op_return_protocol', 'unknown')
            data_utf8 = o.get('op_return_data_utf8')

            # Enhanced protocol detection
            if protocol == 'unknown' and data_hex:
                protocol = _classify_protocol(data_hex, data_utf8)

            op_return_outputs.append({
                'index': i,
                'protocol': protocol,
                'data_hex': data_hex[:128] if data_hex else '',
                'data_size': len(data_hex) // 2 if data_hex else 0
            })

    if op_return_outputs:
        return {
            'detected': True,
            'op_return_count': len(op_return_outputs),
            'outputs': op_return_outputs,
            'confidence': 'high'
        }

    return {'detected': False}


def _classify_protocol(data_hex, data_utf8=None):
    """Classify OP_RETURN data by protocol prefix."""
    if not data_hex:
        return 'unknown'

    data_lower = data_hex.lower()

    # Omni Layer: starts with "omni" (6f6d6e69)
    if data_lower.startswith('6f6d6e69'):
        return 'omni'

    # OpenTimestamps: starts with 0109f91102
    if data_lower.startswith('0109f91102'):
        return 'opentimestamps'

    # Counterparty: starts with "CNTRPRTY" (434e545250525459)
    if data_lower.startswith('434e545250525459'):
        return 'counterparty'

    # Stacks commit (STX)
    if data_lower.startswith('5354'):
        return 'stacks'

    # RUNES protocol — OP_13 magic byte (0x5d) as first byte of data push,
    # or the older convention of 'd8' prefix
    if data_lower.startswith('5d') or data_lower.startswith('d8'):
        return 'runes'

    # Check for UTF-8 text content
    if data_utf8 and all(32 <= ord(c) <= 126 for c in data_utf8):
        return 'text'

    return 'unknown'
