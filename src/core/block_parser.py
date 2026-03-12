"""
Bitcoin block parser

Parses Bitcoin Core block files (blk*.dat) and computes block analysis.
Uses undo data from rev*.dat for prevout information.

Reference:
- https://developer.bitcoin.org/reference/block_chain.html
- https://github.com/bitcoin/bitcoin/blob/master/src/primitives/block.h
"""

import struct
from .varint import read_varint, encode_varint
from .crypto import double_sha256, reverse_bytes
from .merkle import compute_merkle_root
from .script_parser import (
    disassemble_script,
    classify_output_script,
    extract_op_return_data,
    scriptpubkey_to_address
)
from .tx_parser import classify_input_script, parse_relative_timelock


MAINNET_MAGIC = b'\xf9\xbe\xb4\xd9'
TESTNET_MAGIC = b'\x0b\x11\x09\x07'


def apply_xor_decryption(data, xor_key):
    """
    Apply XOR decryption using Bitcoin Core's obfuscation method.

    Uses big-integer XOR for O(1) bitwise operations on the entire buffer,
    which is orders of magnitude faster than byte-by-byte iteration in Python
    for large block files (100MB+).
    """
    if not xor_key:
        return data
    data_len = len(data)
    if data_len == 0:
        return data
    key_len = len(xor_key)
    # Build repeated key to match data length
    repeats = (data_len // key_len) + 1
    full_key = (xor_key * repeats)[:data_len]
    # XOR via big integers — GMP-backed, extremely fast
    data_int = int.from_bytes(data, 'big')
    key_int = int.from_bytes(full_key, 'big')
    return (data_int ^ key_int).to_bytes(data_len, 'big')


def parse_block_header(header_bytes):
    """
    Parse 80-byte block header.

    Returns:
        dict with: version, prev_block_hash, merkle_root, timestamp, bits, nonce, block_hash
    """
    if len(header_bytes) != 80:
        raise ValueError(f"Invalid block header size: {len(header_bytes)} (expected 80)")

    version = struct.unpack('<I', header_bytes[0:4])[0]
    prev_block_hash = reverse_bytes(header_bytes[4:36]).hex()
    merkle_root = reverse_bytes(header_bytes[36:68]).hex()
    timestamp = struct.unpack('<I', header_bytes[68:72])[0]
    bits = header_bytes[72:76].hex()
    nonce = struct.unpack('<I', header_bytes[76:80])[0]

    block_hash = reverse_bytes(double_sha256(header_bytes)).hex()

    return {
        'version': version,
        'prev_block_hash': prev_block_hash,
        'merkle_root': merkle_root,
        'timestamp': timestamp,
        'bits': bits,
        'nonce': nonce,
        'block_hash': block_hash
    }


def parse_blocks_from_file(blk_file_path, undo_data=None, network='mainnet', xor_file_path=None, full_tx_block_indices=None):
    """
    Parse all blocks from a blk*.dat file.

    Args:
        blk_file_path: path to blk*.dat file
        undo_data: list of undo dicts from parse_undo_file(), each with:
            - 'num_txs': int
            - 'tx_undos': list of tx_undos
            - 'raw_bytes': bytes (for checksum verification)
            - 'checksum': 32-byte hash or None
        network: 'mainnet' or 'testnet'
        xor_file_path: path to XOR key file
        full_tx_block_indices: set of block indices that need full tx detail
                               (script_asm, etc). None = all blocks get full detail.

    Returns:
        list of block analysis dicts
    """
    # Read XOR key
    xor_key = b''
    if xor_file_path:
        try:
            with open(xor_file_path, 'rb') as f:
                xor_key = f.read()
        except Exception:
            xor_key = b''

    with open(blk_file_path, 'rb') as f:
        data = f.read()

    # Apply XOR decryption if key is present and non-zero
    if xor_key and any(b != 0 for b in xor_key):
        data = apply_xor_decryption(data, xor_key)

    # Build undo lookup by num_txs for matching
    undo_lookup = {}
    if undo_data:
        for entry in undo_data:
            key = entry['num_txs']
            if key not in undo_lookup:
                undo_lookup[key] = []
            undo_lookup[key].append(entry)

    blocks = []
    offset = 0
    has_errors = False
    block_idx = 0

    while offset < len(data):
        if offset + 4 > len(data):
            break

        magic = data[offset:offset + 4]
        if magic != MAINNET_MAGIC and magic != TESTNET_MAGIC:
            # Scan forward for next magic bytes (handles padding/garbage between blocks)
            found = False
            scan_limit = min(offset + 16, len(data) - 4)
            for scan in range(offset + 1, scan_limit + 1):
                if data[scan:scan + 4] in (MAINNET_MAGIC, TESTNET_MAGIC):
                    offset = scan
                    found = True
                    break
            if not found:
                break
            continue

        offset += 4

        if offset + 4 > len(data):
            break
        block_size = struct.unpack('<I', data[offset:offset + 4])[0]
        offset += 4

        if block_size == 0 or block_size > 4200000:
            break

        if offset + block_size > len(data):
            break
        block_data = data[offset:offset + block_size]
        offset += block_size

        # Match undo data to this block using tx count and checksum
        block_undo = _find_matching_undo(block_data, undo_lookup)

        # Determine if this block needs full tx detail (script_asm, etc.)
        lean = True
        if full_tx_block_indices is None or block_idx in full_tx_block_indices:
            lean = False

        try:
            block_result = parse_single_block(block_data, block_undo, network, lean=lean)
            blocks.append(block_result)
            # Track errors from parsed blocks (e.g. Merkle mismatch)
            if not block_result.get('ok', False):
                has_errors = True
        except Exception as e:
            has_errors = True
            blocks.append({
                'ok': False,
                'error': {
                    'code': 'BLOCK_PARSE_ERROR',
                    'message': str(e)
                }
            })
            # Continue parsing remaining blocks rather than aborting
        block_idx += 1

    return blocks, has_errors


def _find_matching_undo(block_data, undo_lookup):
    """
    Find the matching undo data for a block by tx count.
    For ambiguous matches (same tx count), verify with checksum.

    Args:
        block_data: raw block bytes
        undo_lookup: dict {num_txs: [undo_entry_dicts]}

    Returns:
        list of tx_undos (one per non-coinbase tx), or None
    """
    if not undo_lookup:
        return None

    # Get non-coinbase tx count from block data
    tx_count, _ = read_varint(block_data, 80)
    non_coinbase = tx_count - 1

    candidates = undo_lookup.get(non_coinbase)
    if not candidates:
        return None

    if len(candidates) == 1:
        # Unique match — use it and remove from lookup
        entry = candidates.pop(0)
        if not candidates:
            del undo_lookup[non_coinbase]
        return entry['tx_undos']

    # Multiple candidates — disambiguate using checksum
    # checksum = sha256d(block_hash_internal_bytes + undo_raw_bytes)
    header_bytes = block_data[0:80]
    block_hash_bytes = double_sha256(header_bytes)  # internal byte order

    for i, cand in enumerate(candidates):
        if cand['checksum'] is not None:
            expected = double_sha256(block_hash_bytes + cand['raw_bytes'])
            if expected == cand['checksum']:
                candidates.pop(i)
                if not candidates:
                    del undo_lookup[non_coinbase]
                return cand['tx_undos']

    # Fallback: use first candidate
    entry = candidates.pop(0)
    if not candidates:
        del undo_lookup[non_coinbase]
    return entry['tx_undos']


def parse_single_block(block_data, block_undo, network, lean=False):
    """
    Parse a single block with full transaction analysis.

    Args:
        block_data: raw block bytes (after magic + size header)
        block_undo: list of tx_undos from undo parser (one per non-coinbase tx),
                    or None if undo data unavailable
        network: 'mainnet' or 'testnet'
        lean: if True, skip expensive script_asm and address computation

    Returns:
        dict with block analysis
    """
    offset = 0

    # Parse 80-byte header
    header = parse_block_header(block_data[offset:offset + 80])
    offset += 80

    # Transaction count
    tx_count, offset = read_varint(block_data, offset)

    # Parse all transactions
    tx_hashes_for_merkle = []
    transactions = []
    undo_tx_index = 0  # Index into block_undo (skips coinbase)

    for tx_index in range(tx_count):
        # Extract raw transaction bytes
        tx_bytes, new_offset = extract_transaction_bytes(block_data, offset)
        offset = new_offset

        # Compute txid for Merkle tree
        txid_bytes = compute_txid_bytes(tx_bytes)
        tx_hashes_for_merkle.append(txid_bytes)

        if tx_index == 0:
            # Coinbase transaction
            tx_result = parse_coinbase_tx_full(tx_bytes, network, lean=lean)
        else:
            # Non-coinbase transaction - use undo prevouts if available
            prevouts = None
            if block_undo and undo_tx_index < len(block_undo):
                prevouts = block_undo[undo_tx_index]
            undo_tx_index += 1

            tx_result = parse_block_tx_full(tx_bytes, prevouts, network, lean=lean)

        transactions.append(tx_result)

    # Compute Merkle root
    computed_merkle_root = compute_merkle_root(tx_hashes_for_merkle)
    computed_merkle_root_hex = reverse_bytes(computed_merkle_root).hex()
    merkle_root_valid = (computed_merkle_root_hex == header['merkle_root'])

    if not merkle_root_valid:
        return {
            'ok': False,
            'error': {
                'code': 'MERKLE_ROOT_MISMATCH',
                'message': f"Computed merkle root {computed_merkle_root_hex} does not match header {header['merkle_root']}"
            }
        }

    # Extract coinbase info
    coinbase_tx = transactions[0]
    coinbase_info = {
        'bip34_height': coinbase_tx.get('bip34_height'),
        'coinbase_script_hex': coinbase_tx.get('coinbase_script_hex', ''),
        'total_output_sats': coinbase_tx.get('total_output_sats', 0)
    }

    # Compute block stats
    total_fees = sum(tx.get('fee_sats', 0) for tx in transactions[1:] if tx.get('ok', False))
    total_weight = sum(tx.get('weight', 0) for tx in transactions if tx.get('ok', False))

    # Average fee rate (only non-coinbase txs with vbytes > 0)
    fee_rate_sum = 0
    fee_rate_count = 0
    for tx in transactions[1:]:
        if tx.get('ok', False) and tx.get('vbytes', 0) > 0 and tx.get('fee_sats', 0) > 0:
            fee_rate_sum += tx['fee_sats'] / tx['vbytes']
            fee_rate_count += 1
    avg_fee_rate = fee_rate_sum / fee_rate_count if fee_rate_count > 0 else 0

    # Script type summary (from all outputs of all transactions)
    script_type_summary = {}
    for tx in transactions:
        if tx.get('ok', False):
            for vout in tx.get('vout', []):
                stype = vout.get('script_type', 'unknown')
                script_type_summary[stype] = script_type_summary.get(stype, 0) + 1

    return {
        'ok': True,
        'mode': 'block',
        'block_header': {
            **header,
            'merkle_root_valid': merkle_root_valid
        },
        'tx_count': tx_count,
        'coinbase': coinbase_info,
        'transactions': transactions,
        'block_stats': {
            'total_fees_sats': total_fees,
            'total_weight': total_weight,
            'avg_fee_rate_sat_vb': round(avg_fee_rate, 2) if avg_fee_rate else 0,
            'script_type_summary': script_type_summary
        }
    }


def extract_transaction_bytes(data, offset):
    """Extract raw transaction bytes from block data."""
    start = offset

    # Version
    offset += 4

    # Check for SegWit marker
    is_segwit = False
    if offset + 2 <= len(data) and data[offset] == 0x00 and data[offset + 1] == 0x01:
        is_segwit = True
        offset += 2

    # Input count
    input_count, offset = read_varint(data, offset)

    for _ in range(input_count):
        offset += 32  # prev txid
        offset += 4   # prev vout
        scriptsig_len, offset = read_varint(data, offset)
        offset += scriptsig_len
        offset += 4   # sequence

    # Output count
    output_count, offset = read_varint(data, offset)

    for _ in range(output_count):
        offset += 8  # value
        scriptpubkey_len, offset = read_varint(data, offset)
        offset += scriptpubkey_len

    # Witness data
    if is_segwit:
        for _ in range(input_count):
            witness_count, offset = read_varint(data, offset)
            for _ in range(witness_count):
                item_len, offset = read_varint(data, offset)
                offset += item_len

    # Locktime
    offset += 4

    return data[start:offset], offset


def compute_txid_bytes(tx_bytes):
    """Compute txid as bytes (internal byte order) for Merkle tree."""
    if len(tx_bytes) > 5 and tx_bytes[4] == 0x00 and tx_bytes[5] == 0x01:
        non_witness_tx = build_non_witness_from_segwit(tx_bytes)
        return double_sha256(non_witness_tx)
    else:
        return double_sha256(tx_bytes)


def build_non_witness_from_segwit(segwit_tx_bytes):
    """Build non-witness serialization from SegWit transaction bytes."""
    offset = 0

    version = segwit_tx_bytes[offset:offset + 4]
    offset += 4

    # Skip marker and flag
    if offset + 2 <= len(segwit_tx_bytes) and segwit_tx_bytes[offset] == 0x00 and segwit_tx_bytes[offset + 1] == 0x01:
        offset += 2

    input_count, offset = read_varint(segwit_tx_bytes, offset)
    inputs_data = [version, encode_varint(input_count)]

    for _ in range(input_count):
        inputs_data.append(segwit_tx_bytes[offset:offset + 32])
        offset += 32
        inputs_data.append(segwit_tx_bytes[offset:offset + 4])
        offset += 4
        scriptsig_len, offset = read_varint(segwit_tx_bytes, offset)
        inputs_data.append(encode_varint(scriptsig_len))
        inputs_data.append(segwit_tx_bytes[offset:offset + scriptsig_len])
        offset += scriptsig_len
        inputs_data.append(segwit_tx_bytes[offset:offset + 4])
        offset += 4

    output_count, offset = read_varint(segwit_tx_bytes, offset)
    outputs_data = [encode_varint(output_count)]

    for _ in range(output_count):
        outputs_data.append(segwit_tx_bytes[offset:offset + 8])
        offset += 8
        scriptpubkey_len, offset = read_varint(segwit_tx_bytes, offset)
        outputs_data.append(encode_varint(scriptpubkey_len))
        outputs_data.append(segwit_tx_bytes[offset:offset + scriptpubkey_len])
        offset += scriptpubkey_len

    locktime = segwit_tx_bytes[-4:]
    return b''.join(inputs_data + outputs_data) + locktime


def parse_coinbase_tx_full(tx_bytes, network='mainnet', lean=False):
    """
    Parse coinbase transaction fully, including outputs.

    Returns complete transaction analysis dict with coinbase-specific fields.
    """
    raw_tx = tx_bytes
    offset = 0

    version = struct.unpack('<I', raw_tx[offset:offset + 4])[0]
    offset += 4

    is_segwit = False
    if offset + 2 <= len(raw_tx) and raw_tx[offset] == 0x00 and raw_tx[offset + 1] == 0x01:
        is_segwit = True
        offset += 2

    input_count, offset = read_varint(raw_tx, offset)

    # Coinbase input
    prev_txid_raw = raw_tx[offset:offset + 32]
    prev_txid = reverse_bytes(prev_txid_raw).hex()
    offset += 32
    prev_vout = struct.unpack('<I', raw_tx[offset:offset + 4])[0]
    offset += 4

    scriptsig_len, offset = read_varint(raw_tx, offset)
    coinbase_script = raw_tx[offset:offset + scriptsig_len]
    offset += scriptsig_len

    sequence = struct.unpack('<I', raw_tx[offset:offset + 4])[0]
    offset += 4

    # BIP34 height
    bip34_height = extract_bip34_height(coinbase_script)

    # Validate coinbase transaction structure
    # Must have exactly one input
    if input_count != 1:
        raise ValueError(f"Coinbase transaction must have exactly 1 input, got {input_count}")
    # Previous txid must be all zeros
    if prev_txid != '0' * 64:
        raise ValueError(f"Coinbase input txid must be 0x00...00, got {prev_txid}")
    # Previous vout must be 0xFFFFFFFF
    if prev_vout != 0xFFFFFFFF:
        raise ValueError(f"Coinbase input vout must be 0xFFFFFFFF, got {prev_vout:#010x}")

    # Parse outputs
    output_count, offset = read_varint(raw_tx, offset)
    vout_data = []
    total_output_value = 0

    for i in range(output_count):
        value = struct.unpack('<Q', raw_tx[offset:offset + 8])[0]
        offset += 8
        total_output_value += value

        spk_len, offset = read_varint(raw_tx, offset)
        scriptpubkey = raw_tx[offset:offset + spk_len]
        offset += spk_len

        script_hex = scriptpubkey.hex()
        script_type = classify_output_script(script_hex)
        address = scriptpubkey_to_address(script_hex, network) if not lean else None

        vout_entry = {
            'n': i,
            'value_sats': value,
            'script_pubkey_hex': script_hex,
            'script_asm': disassemble_script(script_hex) if not lean else '',
            'script_type': script_type,
            'address': address
        }
        if script_type == 'op_return':
            vout_entry.update(extract_op_return_data(script_hex))
        vout_data.append(vout_entry)

    # Parse witness
    witnesses = []
    if is_segwit:
        for _ in range(input_count):
            wcount, offset = read_varint(raw_tx, offset)
            witems = []
            for _ in range(wcount):
                wlen, offset = read_varint(raw_tx, offset)
                witems.append(raw_tx[offset:offset + wlen].hex())
                offset += wlen
            witnesses.append(witems)
    else:
        witnesses = [[] for _ in range(input_count)]

    locktime = struct.unpack('<I', raw_tx[offset:offset + 4])[0]

    # Compute txid
    if is_segwit:
        non_witness_tx = build_non_witness_from_segwit(raw_tx)
        txid = reverse_bytes(double_sha256(non_witness_tx)).hex()
        wtxid = reverse_bytes(double_sha256(raw_tx)).hex()
    else:
        txid = reverse_bytes(double_sha256(raw_tx)).hex()
        wtxid = None
        non_witness_tx = None

    # Sizes
    total_size = len(raw_tx)
    if is_segwit:
        non_witness_size = len(non_witness_tx)  # Reuse cached result
        witness_size = total_size - non_witness_size - 2
        weight = non_witness_size * 4 + witness_size + 2
    else:
        non_witness_size = total_size
        witness_size = 0
        weight = total_size * 4
    vbytes = (weight + 3) // 4

    # Coinbase vin
    vin_data = [{
        'txid': prev_txid,
        'vout': prev_vout,
        'sequence': sequence,
        'script_sig_hex': coinbase_script.hex(),
        'script_asm': disassemble_script(coinbase_script.hex()) if not lean else '',
        'witness': witnesses[0] if witnesses else [],
        'script_type': 'coinbase',
        'address': None,
        'prevout': None,
        'relative_timelock': {'enabled': False}
    }]

    return {
        'ok': True,
        'network': network,
        'segwit': is_segwit,
        'txid': txid,
        'wtxid': wtxid,
        'version': version,
        'locktime': locktime,
        'size_bytes': total_size,
        'weight': weight,
        'vbytes': vbytes,
        'total_input_sats': 0,
        'total_output_sats': total_output_value,
        'fee_sats': 0,
        'fee_rate_sat_vb': 0,
        'rbf_signaling': False,
        'locktime_type': 'none',
        'locktime_value': locktime,
        'segwit_savings': None,
        'vin': vin_data,
        'vout': vout_data,
        'warnings': [],
        'is_coinbase': True,
        'bip34_height': bip34_height,
        'coinbase_script_hex': coinbase_script.hex()
    }


def parse_block_tx_full(tx_bytes, undo_prevouts, network='mainnet', lean=False):
    """
    Parse a non-coinbase transaction in block mode with undo prevouts.

    Args:
        tx_bytes: raw transaction bytes
        undo_prevouts: list of prevout dicts from undo parser, one per input
                       (in the same order as inputs). None if unavailable.
        network: 'mainnet' or 'testnet'
        lean: if True, skip expensive script_asm and minimize address computation

    Returns:
        Complete transaction analysis dict
    """
    raw_tx = tx_bytes
    offset = 0

    version = struct.unpack('<I', raw_tx[offset:offset + 4])[0]
    offset += 4

    is_segwit = False
    if offset + 2 <= len(raw_tx) and raw_tx[offset] == 0x00 and raw_tx[offset + 1] == 0x01:
        is_segwit = True
        offset += 2

    input_count, offset = read_varint(raw_tx, offset)

    # Parse inputs
    inputs = []
    for _ in range(input_count):
        prev_txid = reverse_bytes(raw_tx[offset:offset + 32]).hex()
        offset += 32
        prev_vout = struct.unpack('<I', raw_tx[offset:offset + 4])[0]
        offset += 4
        scriptsig_len, offset = read_varint(raw_tx, offset)
        scriptsig = raw_tx[offset:offset + scriptsig_len]
        offset += scriptsig_len
        sequence = struct.unpack('<I', raw_tx[offset:offset + 4])[0]
        offset += 4

        inputs.append({
            'txid': prev_txid,
            'vout': prev_vout,
            'script_sig': scriptsig,
            'sequence': sequence
        })

    # Parse outputs
    output_count, offset = read_varint(raw_tx, offset)
    outputs = []
    for _ in range(output_count):
        value = struct.unpack('<Q', raw_tx[offset:offset + 8])[0]
        offset += 8
        spk_len, offset = read_varint(raw_tx, offset)
        scriptpubkey = raw_tx[offset:offset + spk_len]
        offset += spk_len
        outputs.append({'value': value, 'script_pubkey': scriptpubkey})

    # Parse witness
    witnesses = []
    if is_segwit:
        for _ in range(input_count):
            wcount, offset = read_varint(raw_tx, offset)
            witems = []
            for _ in range(wcount):
                wlen, offset = read_varint(raw_tx, offset)
                witems.append(raw_tx[offset:offset + wlen].hex())
                offset += wlen
            witnesses.append(witems)
    else:
        witnesses = [[] for _ in range(input_count)]

    locktime = struct.unpack('<I', raw_tx[offset:offset + 4])[0]

    # Compute txid / wtxid
    if is_segwit:
        non_witness_tx = build_non_witness_from_segwit(raw_tx)
        txid = reverse_bytes(double_sha256(non_witness_tx)).hex()
        wtxid = reverse_bytes(double_sha256(raw_tx)).hex()
    else:
        txid = reverse_bytes(double_sha256(raw_tx)).hex()
        wtxid = None
        non_witness_tx = None

    # Sizes per BIP141
    total_size = len(raw_tx)
    if is_segwit:
        non_witness_size = len(non_witness_tx)  # Reuse cached result
        witness_size = total_size - non_witness_size - 2
        weight = non_witness_size * 4 + witness_size + 2
    else:
        non_witness_size = total_size
        witness_size = 0
        weight = total_size * 4
    vbytes = (weight + 3) // 4

    # Build vin with prevout data from undo
    total_input_value = 0
    vin_data = []

    for i, inp in enumerate(inputs):
        prevout = None
        if undo_prevouts and i < len(undo_prevouts):
            prevout = undo_prevouts[i]

        if prevout:
            total_input_value += prevout['value_sats']
            input_script_type = classify_input_script(
                prevout['script_pubkey_hex'],
                inp['script_sig'].hex(),
                witnesses[i]
            )
            address = scriptpubkey_to_address(prevout['script_pubkey_hex'], network) if not lean else None
        else:
            input_script_type = 'unknown'
            address = None

        relative_timelock = parse_relative_timelock(inp['sequence'], version)

        vin_entry = {
            'txid': inp['txid'],
            'vout': inp['vout'],
            'sequence': inp['sequence'],
            'script_sig_hex': inp['script_sig'].hex(),
            'script_asm': disassemble_script(inp['script_sig'].hex()) if not lean else '',
            'witness': witnesses[i],
            'script_type': input_script_type,
            'address': address,
            'prevout': {
                'value_sats': prevout['value_sats'],
                'script_pubkey_hex': prevout['script_pubkey_hex']
            } if prevout else None,
            'relative_timelock': relative_timelock
        }

        # witness_script_asm for P2WSH and P2SH-P2WSH
        if not lean and input_script_type in ('p2wsh', 'p2sh-p2wsh') and len(witnesses[i]) > 0:
            vin_entry['witness_script_asm'] = disassemble_script(witnesses[i][-1])

        vin_data.append(vin_entry)

    # Build vout
    total_output_value = 0
    vout_data = []

    for i, out in enumerate(outputs):
        total_output_value += out['value']
        script_hex = out['script_pubkey'].hex()
        script_type = classify_output_script(script_hex)
        address = scriptpubkey_to_address(script_hex, network) if not lean else None

        vout_entry = {
            'n': i,
            'value_sats': out['value'],
            'script_pubkey_hex': script_hex,
            'script_asm': disassemble_script(script_hex) if not lean else '',
            'script_type': script_type,
            'address': address
        }
        if script_type == 'op_return':
            vout_entry.update(extract_op_return_data(script_hex))
        vout_data.append(vout_entry)

    # Fee calculation
    # In block mode, undo data may not perfectly align (different block counts,
    # partial prevouts), so we clamp negative fees to 0 rather than erroring.
    fee = total_input_value - total_output_value if undo_prevouts else 0
    if fee < 0:
        fee = 0  # Undo data misalignment — clamp rather than error
    fee_rate = fee / vbytes if vbytes > 0 and fee > 0 else 0

    # RBF
    rbf_signaling = any(inp['sequence'] < 0xFFFFFFFE for inp in inputs)

    # Locktime
    if locktime == 0:
        locktime_type = "none"
    elif locktime < 500000000:
        locktime_type = "block_height"
    else:
        locktime_type = "unix_timestamp"

    # Warnings
    warnings = []
    if fee > 1000000 or fee_rate > 200:
        warnings.append({'code': 'HIGH_FEE'})
    for vout in vout_data:
        if vout['script_type'] != 'op_return' and vout['value_sats'] < 546:
            warnings.append({'code': 'DUST_OUTPUT'})
            break
    if any(vout['script_type'] == 'unknown' for vout in vout_data):
        warnings.append({'code': 'UNKNOWN_OUTPUT_SCRIPT'})
    if rbf_signaling:
        warnings.append({'code': 'RBF_SIGNALING'})

    # SegWit savings
    segwit_savings = None
    if is_segwit:
        weight_if_legacy = non_witness_size * 4
        savings_pct = ((weight_if_legacy - weight) / weight_if_legacy * 100) if weight_if_legacy > 0 else 0
        segwit_savings = {
            'witness_bytes': witness_size,
            'non_witness_bytes': non_witness_size,
            'total_bytes': total_size,
            'weight_actual': weight,
            'weight_if_legacy': weight_if_legacy,
            'savings_pct': round(savings_pct, 2)
        }

    return {
        'ok': True,
        'network': network,
        'segwit': is_segwit,
        'txid': txid,
        'wtxid': wtxid,
        'version': version,
        'locktime': locktime,
        'size_bytes': total_size,
        'weight': weight,
        'vbytes': vbytes,
        'total_input_sats': total_input_value,
        'total_output_sats': total_output_value,
        'fee_sats': fee,
        'fee_rate_sat_vb': round(fee_rate, 2),
        'rbf_signaling': rbf_signaling,
        'locktime_type': locktime_type,
        'locktime_value': locktime,
        'segwit_savings': segwit_savings,
        'vin': vin_data,
        'vout': vout_data,
        'warnings': warnings,
        'is_coinbase': False
    }


def extract_bip34_height(coinbase_script):
    """
    Extract block height from coinbase scriptSig per BIP34.

    The first push in the coinbase scriptSig encodes the block height
    as a little-endian integer.
    """
    if len(coinbase_script) == 0:
        return None

    push_len = coinbase_script[0]
    if push_len == 0 or push_len > 5:
        return None
    if len(coinbase_script) < 1 + push_len:
        return None

    height_bytes = coinbase_script[1:1 + push_len]
    return int.from_bytes(height_bytes, 'little')
