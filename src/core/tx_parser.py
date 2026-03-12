"""
Bitcoin transaction parser

Parses raw Bitcoin transactions (legacy and SegWit) and computes all required fields.

References:
- https://developer.bitcoin.org/reference/transactions.html
- BIP141 (SegWit): https://github.com/bitcoin/bips/blob/master/bip-0141.mediawiki
- BIP125 (RBF): https://github.com/bitcoin/bips/blob/master/bip-0125.mediawiki
- BIP68 (Relative locktime): https://github.com/bitcoin/bips/blob/master/bip-0068.mediawiki
"""

import struct
from .varint import read_varint
from .crypto import double_sha256, reverse_bytes
from .script_parser import (
    disassemble_script, 
    classify_output_script, 
    extract_op_return_data,
    scriptpubkey_to_address
)


def parse_transaction(raw_tx_hex, prevouts_list, network='mainnet'):
    """
    Parse a raw Bitcoin transaction and compute all required fields.
    
    Args:
        raw_tx_hex: str (hex-encoded transaction)
        prevouts_list: list of dicts with keys: txid, vout, value_sats, script_pubkey_hex
        network: str ('mainnet' or 'testnet')
    
    Returns:
        dict with all transaction fields per spec
    """
    raw_tx = bytes.fromhex(raw_tx_hex)
    
    # Create prevout lookup map — EC2: detect duplicate prevout entries
    prevout_map = {}
    for prevout in prevouts_list:
        key = (prevout['txid'], prevout['vout'])
        if key in prevout_map:
            raise ValueError(f"Duplicate prevout entry: txid={prevout['txid']}, vout={prevout['vout']}")
        prevout_map[key] = prevout
    
    # Parse transaction structure
    offset = 0
    
    # Version (4 bytes, little-endian)
    version = struct.unpack('<I', raw_tx[offset:offset+4])[0]
    offset += 4
    
    # Check for SegWit marker
    is_segwit = False
    if offset + 2 <= len(raw_tx) and raw_tx[offset] == 0x00 and raw_tx[offset+1] == 0x01:
        is_segwit = True
        offset += 2  # Skip marker and flag
    
    # Input count
    input_count, offset = read_varint(raw_tx, offset)
    
    # EC1: Zero-input transaction is invalid
    if input_count == 0:
        raise ValueError("Transaction has zero inputs")
    
    # Parse inputs
    inputs = []
    for _ in range(input_count):
        # Previous txid (32 bytes, reversed for display)
        prev_txid = reverse_bytes(raw_tx[offset:offset+32]).hex()
        offset += 32
        
        # Previous vout (4 bytes, little-endian)
        prev_vout = struct.unpack('<I', raw_tx[offset:offset+4])[0]
        offset += 4
        
        # ScriptSig length and data
        scriptsig_len, offset = read_varint(raw_tx, offset)
        scriptsig = raw_tx[offset:offset+scriptsig_len]
        offset += scriptsig_len
        
        # Sequence (4 bytes, little-endian)
        sequence = struct.unpack('<I', raw_tx[offset:offset+4])[0]
        offset += 4
        
        inputs.append({
            'txid': prev_txid,
            'vout': prev_vout,
            'script_sig': scriptsig,
            'sequence': sequence
        })
    
    # Output count
    output_count, offset = read_varint(raw_tx, offset)
    
    # EC1: Zero-output transaction is invalid
    if output_count == 0:
        raise ValueError("Transaction has zero outputs")
    
    # Parse outputs
    outputs = []
    for _ in range(output_count):
        # Value (8 bytes, little-endian)
        value = struct.unpack('<Q', raw_tx[offset:offset+8])[0]
        offset += 8
        
        # ScriptPubKey length and data
        scriptpubkey_len, offset = read_varint(raw_tx, offset)
        scriptpubkey = raw_tx[offset:offset+scriptpubkey_len]
        offset += scriptpubkey_len
        
        outputs.append({
            'value': value,
            'script_pubkey': scriptpubkey
        })
    
    # Parse witness data (if SegWit)
    witnesses = []
    if is_segwit:
        for _ in range(input_count):
            witness_count, offset = read_varint(raw_tx, offset)
            witness_items = []
            for _ in range(witness_count):
                item_len, offset = read_varint(raw_tx, offset)
                item = raw_tx[offset:offset+item_len]
                offset += item_len
                witness_items.append(item.hex())
            witnesses.append(witness_items)
    else:
        # Legacy tx: empty witness for each input
        witnesses = [[] for _ in range(input_count)]
    
    # Locktime (4 bytes, little-endian)
    locktime = struct.unpack('<I', raw_tx[offset:offset+4])[0]
    offset += 4
    
    # Compute txid (non-witness serialization)
    if is_segwit:
        # Rebuild without witness data
        non_witness_tx = build_non_witness_tx(version, inputs, outputs, locktime)
        txid = reverse_bytes(double_sha256(non_witness_tx)).hex()
    else:
        txid = reverse_bytes(double_sha256(raw_tx)).hex()
    
    # Compute wtxid (full serialization including witness)
    if is_segwit:
        wtxid = reverse_bytes(double_sha256(raw_tx)).hex()
    else:
        wtxid = None
    
    # Compute size, weight, vbytes according to BIP141
    total_size = len(raw_tx)
    if is_segwit:
        non_witness_size = len(build_non_witness_tx(version, inputs, outputs, locktime))
        witness_size = total_size - non_witness_size - 2  # Subtract marker and flag
        weight = non_witness_size * 4 + witness_size + 2  # Include marker and flag in witness
        vbytes = (weight + 3) // 4  # Ceiling division per BIP141
    else:
        non_witness_size = total_size
        witness_size = 0
        weight = total_size * 4
        vbytes = total_size
    
    # Match prevouts to inputs
    total_input_value = 0
    vin_data = []
    consumed_prevout_keys = set()
    
    for i, inp in enumerate(inputs):
        key = (inp['txid'], inp['vout'])
        if key not in prevout_map:
            raise ValueError(f"Missing prevout for input {i}: txid={inp['txid']}, vout={inp['vout']}")
        
        consumed_prevout_keys.add(key)
        prevout = prevout_map[key]
        total_input_value += prevout['value_sats']
        
        # Classify input script type
        input_script_type = classify_input_script(
            prevout['script_pubkey_hex'],
            inp['script_sig'].hex(),
            witnesses[i]
        )
        
        # Get address from prevout scriptPubKey
        address = scriptpubkey_to_address(prevout['script_pubkey_hex'], network)
        
        # Parse relative timelock (BIP68) — only meaningful for version >= 2
        relative_timelock = parse_relative_timelock(inp['sequence'], version)
        
        # Build vin entry
        vin_entry = {
            'txid': inp['txid'],
            'vout': inp['vout'],
            'sequence': inp['sequence'],
            'script_sig_hex': inp['script_sig'].hex(),
            'script_asm': disassemble_script(inp['script_sig'].hex()),
            'witness': witnesses[i],
            'script_type': input_script_type,
            'address': address,
            'prevout': {
                'value_sats': prevout['value_sats'],
                'script_pubkey_hex': prevout['script_pubkey_hex']
            },
            'relative_timelock': relative_timelock
        }
        
        # Add witness_script_asm for P2WSH and P2SH-P2WSH
        if input_script_type in ['p2wsh', 'p2sh-p2wsh'] and len(witnesses[i]) > 0:
            witness_script_hex = witnesses[i][-1]
            vin_entry['witness_script_asm'] = disassemble_script(witness_script_hex)
        
        vin_data.append(vin_entry)
    
    # EC3: Check for unconsumed (extra) prevout entries
    unconsumed = set(prevout_map.keys()) - consumed_prevout_keys
    if unconsumed:
        extra = list(unconsumed)[0]
        raise ValueError(f"Extra prevout not matching any input: txid={extra[0]}, vout={extra[1]}")
    
    # Process outputs
    total_output_value = 0
    vout_data = []
    
    for i, out in enumerate(outputs):
        total_output_value += out['value']
        
        script_hex = out['script_pubkey'].hex()
        script_type = classify_output_script(script_hex)
        address = scriptpubkey_to_address(script_hex, network)
        
        vout_entry = {
            'n': i,
            'value_sats': out['value'],
            'script_pubkey_hex': script_hex,
            'script_asm': disassemble_script(script_hex),
            'script_type': script_type,
            'address': address
        }
        
        # Add OP_RETURN data if applicable
        if script_type == 'op_return':
            op_return_info = extract_op_return_data(script_hex)
            vout_entry.update(op_return_info)
        
        vout_data.append(vout_entry)
    
    # Compute fee — EC5: guard against negative fee
    fee = total_input_value - total_output_value
    if fee < 0:
        raise ValueError(f"Negative fee: total_output_sats ({total_output_value}) exceeds total_input_sats ({total_input_value})")
    fee_rate = fee / vbytes if vbytes > 0 else 0
    
    # Detect RBF signaling (BIP125)
    rbf_signaling = any(inp['sequence'] < 0xFFFFFFFE for inp in inputs)
    
    # Classify locktime
    if locktime == 0:
        locktime_type = "none"
    elif locktime < 500000000:
        locktime_type = "block_height"
    else:
        locktime_type = "unix_timestamp"
    
    # Detect warnings
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
    
    # Compute SegWit savings according to BIP141
    segwit_savings = None
    if is_segwit:
        # weight_if_legacy: weight this tx would have if serialized as legacy
        # (no witness data, no marker/flag) = non_witness_size * 4
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
    
    # Build final result
    result = {
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
        'warnings': warnings
    }
    
    return result


def build_non_witness_tx(version, inputs, outputs, locktime):
    """Build non-witness serialization for txid computation."""
    parts = []
    
    # Version
    parts.append(struct.pack('<I', version))
    
    # Input count
    from .varint import encode_varint
    parts.append(encode_varint(len(inputs)))
    
    # Inputs
    for inp in inputs:
        # Txid (reversed)
        parts.append(reverse_bytes(bytes.fromhex(inp['txid'])))
        # Vout
        parts.append(struct.pack('<I', inp['vout']))
        # ScriptSig
        parts.append(encode_varint(len(inp['script_sig'])))
        parts.append(inp['script_sig'])
        # Sequence
        parts.append(struct.pack('<I', inp['sequence']))
    
    # Output count
    parts.append(encode_varint(len(outputs)))
    
    # Outputs
    for out in outputs:
        # Value
        parts.append(struct.pack('<Q', out['value']))
        # ScriptPubKey
        parts.append(encode_varint(len(out['script_pubkey'])))
        parts.append(out['script_pubkey'])
    
    # Locktime
    parts.append(struct.pack('<I', locktime))
    
    return b''.join(parts)


def classify_input_script(prevout_scriptpubkey_hex, scriptsig_hex, witness):
    """
    Classify input spend type per Bitcoin protocol rules.
    
    References:
    - BIP141: https://github.com/bitcoin/bips/blob/master/bip-0141.mediawiki
    - BIP341: https://github.com/bitcoin/bips/blob/master/bip-0341.mediawiki
    
    Returns:
        str: 'p2pkh', 'p2sh-p2wpkh', 'p2sh-p2wsh', 'p2wpkh', 'p2wsh', 
             'p2tr_keypath', 'p2tr_scriptpath', 'unknown'
    """
    prevout_type = classify_output_script(prevout_scriptpubkey_hex)
    has_witness = len(witness) > 0
    scriptsig_len = len(scriptsig_hex) // 2 if scriptsig_hex else 0
    
    # P2PKH: prevout is P2PKH, has scriptSig, no witness
    if prevout_type == 'p2pkh' and scriptsig_len > 0 and not has_witness:
        return 'p2pkh'
    
    # Native P2WPKH: prevout is P2WPKH, empty scriptSig, 2-item witness
    if prevout_type == 'p2wpkh' and scriptsig_len == 0 and len(witness) == 2:
        return 'p2wpkh'
    
    # Native P2WSH: prevout is P2WSH, empty scriptSig, witness present
    if prevout_type == 'p2wsh' and scriptsig_len == 0 and has_witness:
        return 'p2wsh'
    
    # P2SH-wrapped SegWit: prevout is P2SH and has witness data
    # Distinguish P2SH-P2WPKH vs P2SH-P2WSH by examining the redeem script
    # pushed in scriptSig. For P2SH-P2WPKH the redeem script is OP_0 <20-byte-hash>
    # (22 bytes). For P2SH-P2WSH the redeem script is OP_0 <32-byte-hash> (34 bytes).
    if prevout_type == 'p2sh' and has_witness and scriptsig_len > 0:
        try:
            scriptsig_bytes = bytes.fromhex(scriptsig_hex)
            # The scriptSig for nested segwit MUST be a single push of the redeem script.
            # First byte is the push length (direct push 0x01-0x4b).
            push_len = scriptsig_bytes[0]
            if push_len <= 0x4b and 1 + push_len == len(scriptsig_bytes):
                redeem_script = scriptsig_bytes[1:]
                # P2SH-P2WPKH: redeem script = 0x0014{20 bytes} (22 bytes)
                if len(redeem_script) == 22 and redeem_script[0] == 0x00 and redeem_script[1] == 0x14:
                    return 'p2sh-p2wpkh'
                # P2SH-P2WSH: redeem script = 0x0020{32 bytes} (34 bytes)
                if len(redeem_script) == 34 and redeem_script[0] == 0x00 and redeem_script[1] == 0x20:
                    return 'p2sh-p2wsh'
        except Exception:
            pass
        # EC7: No fallback heuristic — if we can't parse the redeem script
        # as a standard nested SegWit form, it's not standard P2SH-SegWit.
        return 'unknown'
    
    # Taproot: prevout is P2TR (OP_1 <32-byte-pubkey>)
    # BIP341: keypath spend has 1 witness item (64 or 65 byte signature)
    # scriptpath spend has 2+ items; last item is control block starting with
    # 0xc0 or 0xc1 (leaf version | parity bit)
    # EC27 / BIP341 annex handling: if the last witness item starts with 0x50,
    # it is the annex. The control block is then the second-to-last item.
    if prevout_type == 'p2tr':
        if len(witness) == 1:
            return 'p2tr_keypath'
        elif len(witness) >= 2:
            # Check for annex: last item starts with 0x50
            effective_witness = list(witness)
            if len(effective_witness) >= 2 and effective_witness[-1] and len(effective_witness[-1]) >= 2:
                last_first_byte = int(effective_witness[-1][0:2], 16)
                if last_first_byte == 0x50:
                    # Annex detected — strip it for control block analysis
                    effective_witness = effective_witness[:-1]
            
            # After stripping annex, if only 1 item remains, it's keypath with annex
            if len(effective_witness) == 1:
                return 'p2tr_keypath'
            
            # Check if last (non-annex) witness item is a control block
            control_block_candidate = effective_witness[-1]
            if control_block_candidate and len(control_block_candidate) >= 2:
                first_byte = int(control_block_candidate[0:2], 16)
                # Control block leaf version: 0xc0 (even) or 0xc1 (odd) for tapscript v1
                # More generally, any byte with bit pattern 110x xxxx could be a control block
                if (first_byte & 0xfe) == 0xc0:
                    return 'p2tr_scriptpath'
            # Fallback: if no recognizable control block but multiple witness items,
            # still classify as scriptpath per the spec
            return 'p2tr_scriptpath'
    
    return 'unknown'


def parse_relative_timelock(sequence, tx_version=2):
    """
    Parse BIP68 relative timelock from sequence number.
    
    Per BIP68, relative timelocks are only enforced when tx.version >= 2.
    For version < 2, all inputs report enabled: False regardless of sequence.
    
    Args:
        sequence: uint32 sequence number
        tx_version: transaction version (BIP68 requires >= 2)
    
    Returns:
        dict with keys: enabled, type (optional), value (optional)
    """
    # BIP68: relative timelocks only apply to transactions with version >= 2
    if tx_version < 2:
        return {'enabled': False}
    
    # Bit 31: if set, relative timelock is disabled
    if sequence & (1 << 31):
        return {'enabled': False}
    
    # Bit 22: if set, time-based (512-second units); otherwise block-based
    if sequence & (1 << 22):
        # Time-based: lower 16 bits × 512 seconds
        value = (sequence & 0xFFFF) * 512
        return {'enabled': True, 'type': 'time', 'value': value}
    else:
        # Block-based: lower 16 bits
        value = sequence & 0xFFFF
        return {'enabled': True, 'type': 'blocks', 'value': value}
