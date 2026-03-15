"""
Bitcoin script parser and disassembler

Implements:
- Script disassembly (hex → ASM format)
- Script type classification
- OP_RETURN data extraction and protocol detection
- Full opcode table support

References:
- https://en.bitcoin.it/wiki/Script
- https://developer.bitcoin.org/devguide/transactions.html
"""

# Bitcoin opcode table
OPCODES = {
    # Constants
    0x00: 'OP_0',
    0x4c: 'OP_PUSHDATA1',
    0x4d: 'OP_PUSHDATA2',
    0x4e: 'OP_PUSHDATA4',
    0x4f: 'OP_1NEGATE',
    0x50: 'OP_RESERVED',
    0x51: 'OP_1',
    0x52: 'OP_2',
    0x53: 'OP_3',
    0x54: 'OP_4',
    0x55: 'OP_5',
    0x56: 'OP_6',
    0x57: 'OP_7',
    0x58: 'OP_8',
    0x59: 'OP_9',
    0x5a: 'OP_10',
    0x5b: 'OP_11',
    0x5c: 'OP_12',
    0x5d: 'OP_13',
    0x5e: 'OP_14',
    0x5f: 'OP_15',
    0x60: 'OP_16',
    
    # Flow control
    0x61: 'OP_NOP',
    0x62: 'OP_VER',
    0x63: 'OP_IF',
    0x64: 'OP_NOTIF',
    0x65: 'OP_VERIF',
    0x66: 'OP_VERNOTIF',
    0x67: 'OP_ELSE',
    0x68: 'OP_ENDIF',
    0x69: 'OP_VERIFY',
    0x6a: 'OP_RETURN',
    
    # Stack
    0x6b: 'OP_TOALTSTACK',
    0x6c: 'OP_FROMALTSTACK',
    0x6d: 'OP_2DROP',
    0x6e: 'OP_2DUP',
    0x6f: 'OP_3DUP',
    0x70: 'OP_2OVER',
    0x71: 'OP_2ROT',
    0x72: 'OP_2SWAP',
    0x73: 'OP_IFDUP',
    0x74: 'OP_DEPTH',
    0x75: 'OP_DROP',
    0x76: 'OP_DUP',
    0x77: 'OP_NIP',
    0x78: 'OP_OVER',
    0x79: 'OP_PICK',
    0x7a: 'OP_ROLL',
    0x7b: 'OP_ROT',
    0x7c: 'OP_SWAP',
    0x7d: 'OP_TUCK',
    
    # Splice
    0x7e: 'OP_CAT',
    0x7f: 'OP_SUBSTR',
    0x80: 'OP_LEFT',
    0x81: 'OP_RIGHT',
    0x82: 'OP_SIZE',
    
    # Bitwise logic
    0x83: 'OP_INVERT',
    0x84: 'OP_AND',
    0x85: 'OP_OR',
    0x86: 'OP_XOR',
    0x87: 'OP_EQUAL',
    0x88: 'OP_EQUALVERIFY',
    0x89: 'OP_RESERVED1',
    0x8a: 'OP_RESERVED2',
    
    # Arithmetic
    0x8b: 'OP_1ADD',
    0x8c: 'OP_1SUB',
    0x8d: 'OP_2MUL',
    0x8e: 'OP_2DIV',
    0x8f: 'OP_NEGATE',
    0x90: 'OP_ABS',
    0x91: 'OP_NOT',
    0x92: 'OP_0NOTEQUAL',
    0x93: 'OP_ADD',
    0x94: 'OP_SUB',
    0x95: 'OP_MUL',
    0x96: 'OP_DIV',
    0x97: 'OP_MOD',
    0x98: 'OP_LSHIFT',
    0x99: 'OP_RSHIFT',
    0x9a: 'OP_BOOLAND',
    0x9b: 'OP_BOOLOR',
    0x9c: 'OP_NUMEQUAL',
    0x9d: 'OP_NUMEQUALVERIFY',
    0x9e: 'OP_NUMNOTEQUAL',
    0x9f: 'OP_LESSTHAN',
    0xa0: 'OP_GREATERTHAN',
    0xa1: 'OP_LESSTHANOREQUAL',
    0xa2: 'OP_GREATERTHANOREQUAL',
    0xa3: 'OP_MIN',
    0xa4: 'OP_MAX',
    0xa5: 'OP_WITHIN',
    
    # Crypto
    0xa6: 'OP_RIPEMD160',
    0xa7: 'OP_SHA1',
    0xa8: 'OP_SHA256',
    0xa9: 'OP_HASH160',
    0xaa: 'OP_HASH256',
    0xab: 'OP_CODESEPARATOR',
    0xac: 'OP_CHECKSIG',
    0xad: 'OP_CHECKSIGVERIFY',
    0xae: 'OP_CHECKMULTISIG',
    0xaf: 'OP_CHECKMULTISIGVERIFY',
    
    # Locktime
    0xb1: 'OP_CHECKLOCKTIMEVERIFY',
    0xb2: 'OP_CHECKSEQUENCEVERIFY',
    
    # NOPs
    0xb0: 'OP_NOP1',
    0xb3: 'OP_NOP4',
    0xb4: 'OP_NOP5',
    0xb5: 'OP_NOP6',
    0xb6: 'OP_NOP7',
    0xb7: 'OP_NOP8',
    0xb8: 'OP_NOP9',
    0xb9: 'OP_NOP10',
}


def disassemble_script(script_hex):
    """
    Disassemble Bitcoin script from hex to ASM format.
    
    Args:
        script_hex: str (hex encoded script)
    
    Returns:
        str (space-separated ASM format)
    
    Format:
        - Opcodes: OP_DUP, OP_HASH160, etc.
        - Data pushes: OP_PUSHBYTES_<n> <hex>
        - Extended pushes: OP_PUSHDATA1/2/4 <hex>
        - Empty script: ""
    """
    if not script_hex:
        return ""
    
    script = bytes.fromhex(script_hex)
    asm_parts = []
    i = 0
    
    while i < len(script):
        opcode = script[i]
        i += 1
        
        # Direct data push (1-75 bytes)
        if 0x01 <= opcode <= 0x4b:
            if i + opcode > len(script):
                # Invalid script, not enough data
                asm_parts.append(f"OP_PUSHBYTES_{opcode} [error:truncated]")
                break
            data = script[i:i+opcode]
            asm_parts.append(f"OP_PUSHBYTES_{opcode} {data.hex()}")
            i += opcode
        
        # OP_PUSHDATA1 (next 1 byte specifies length)
        elif opcode == 0x4c:
            if i >= len(script):
                asm_parts.append("OP_PUSHDATA1 [error:truncated]")
                break
            length = script[i]
            i += 1
            if i + length > len(script):
                asm_parts.append(f"OP_PUSHDATA1 [error:truncated]")
                break
            data = script[i:i+length]
            asm_parts.append(f"OP_PUSHDATA1 {data.hex()}")
            i += length
        
        # OP_PUSHDATA2 (next 2 bytes specify length, little-endian)
        elif opcode == 0x4d:
            if i + 1 >= len(script):
                asm_parts.append("OP_PUSHDATA2 [error:truncated]")
                break
            length = int.from_bytes(script[i:i+2], 'little')
            i += 2
            if i + length > len(script):
                asm_parts.append(f"OP_PUSHDATA2 [error:truncated]")
                break
            data = script[i:i+length]
            asm_parts.append(f"OP_PUSHDATA2 {data.hex()}")
            i += length
        
        # OP_PUSHDATA4 (next 4 bytes specify length, little-endian)
        elif opcode == 0x4e:
            if i + 3 >= len(script):
                asm_parts.append("OP_PUSHDATA4 [error:truncated]")
                break
            length = int.from_bytes(script[i:i+4], 'little')
            i += 4
            if i + length > len(script):
                asm_parts.append(f"OP_PUSHDATA4 [error:truncated]")
                break
            data = script[i:i+length]
            asm_parts.append(f"OP_PUSHDATA4 {data.hex()}")
            i += length
        
        # Regular opcode
        else:
            opcode_name = OPCODES.get(opcode, f"OP_UNKNOWN_<{opcode:#04x}>")
            asm_parts.append(opcode_name)
    
    return ' '.join(asm_parts)


def classify_output_script(script_hex):
    """
    Classify output scriptPubKey type.
    
    Returns:
        str: 'p2pkh', 'p2sh', 'p2wpkh', 'p2wsh', 'p2tr', 'op_return', 'unknown'
    """
    if not script_hex:
        return 'unknown'
    
    script = bytes.fromhex(script_hex)
    script_len = len(script)
    
    # P2PKH: OP_DUP OP_HASH160 <20 bytes> OP_EQUALVERIFY OP_CHECKSIG (25 bytes)
    if script_len == 25 and script[0] == 0x76 and script[1] == 0xa9 and \
       script[2] == 0x14 and script[23] == 0x88 and script[24] == 0xac:
        return 'p2pkh'
    
    # P2SH: OP_HASH160 <20 bytes> OP_EQUAL (23 bytes)
    if script_len == 23 and script[0] == 0xa9 and script[1] == 0x14 and script[22] == 0x87:
        return 'p2sh'
    
    # P2WPKH: OP_0 <20 bytes> (22 bytes)
    if script_len == 22 and script[0] == 0x00 and script[1] == 0x14:
        return 'p2wpkh'
    
    # P2WSH: OP_0 <32 bytes> (34 bytes)
    if script_len == 34 and script[0] == 0x00 and script[1] == 0x20:
        return 'p2wsh'
    
    # P2TR: OP_1 <32 bytes> (34 bytes)
    if script_len == 34 and script[0] == 0x51 and script[1] == 0x20:
        return 'p2tr'
    
    # OP_RETURN: starts with OP_RETURN (0x6a)
    if script[0] == 0x6a:
        return 'op_return'

    # OP_FALSE OP_RETURN variant (0x00 0x6a) — used by some protocols
    if script_len >= 2 and script[0] == 0x00 and script[1] == 0x6a:
        return 'op_return'

    # Bare multisig: OP_n ... OP_m OP_CHECKMULTISIG (0xae)
    if script_len >= 3 and script[-1] == 0xae and 0x51 <= script[0] <= 0x60:
        return 'multisig'

    # Bare P2PK: <33 or 65 byte pubkey> OP_CHECKSIG (0xac)
    if script_len in (35, 67) and script[-1] == 0xac:
        if script_len == 35 and script[0] == 0x21:  # compressed
            return 'p2pk'
        if script_len == 67 and script[0] == 0x41:  # uncompressed
            return 'p2pk'

    return 'unknown'


def extract_op_return_data(script_hex):
    """
    Extract data from OP_RETURN script.
    
    Returns:
        {
            'op_return_data_hex': str (concatenated data pushes),
            'op_return_data_utf8': str or None (UTF-8 decode, None if invalid),
            'op_return_protocol': str ('omni', 'opentimestamps', 'unknown')
        }
    """
    if not script_hex:
        return {'op_return_data_hex': '', 'op_return_data_utf8': None, 'op_return_protocol': 'unknown'}
    
    script = bytes.fromhex(script_hex)
    
    if len(script) == 0:
        return {'op_return_data_hex': '', 'op_return_data_utf8': None, 'op_return_protocol': 'unknown'}

    # Support both bare OP_RETURN and OP_FALSE OP_RETURN
    if script[0] == 0x6a:
        start = 1
    elif len(script) >= 2 and script[0] == 0x00 and script[1] == 0x6a:
        start = 2
    else:
        return {'op_return_data_hex': '', 'op_return_data_utf8': None, 'op_return_protocol': 'unknown'}

    # Extract all data pushes after OP_RETURN
    data_parts = []
    i = start  # Skip OP_RETURN (or OP_FALSE OP_RETURN)
    
    while i < len(script):
        opcode = script[i]
        i += 1
        
        # Direct push
        if 0x01 <= opcode <= 0x4b:
            if i + opcode > len(script):
                break
            data_parts.append(script[i:i+opcode])
            i += opcode
        
        # OP_PUSHDATA1
        elif opcode == 0x4c:
            if i >= len(script):
                break
            length = script[i]
            i += 1
            if i + length > len(script):
                break
            data_parts.append(script[i:i+length])
            i += length
        
        # OP_PUSHDATA2
        elif opcode == 0x4d:
            if i + 1 >= len(script):
                break
            length = int.from_bytes(script[i:i+2], 'little')
            i += 2
            if i + length > len(script):
                break
            data_parts.append(script[i:i+length])
            i += length
        
        # OP_PUSHDATA4
        elif opcode == 0x4e:
            if i + 3 >= len(script):
                break
            length = int.from_bytes(script[i:i+4], 'little')
            i += 4
            if i + length > len(script):
                break
            data_parts.append(script[i:i+length])
            i += length
        
        else:
            # Non-push opcode after OP_RETURN, stop
            break
    
    # Concatenate all data
    data_bytes = b''.join(data_parts)
    data_hex = data_bytes.hex()
    
    # Try UTF-8 decode
    try:
        data_utf8 = data_bytes.decode('utf-8')
    except:
        data_utf8 = None
    
    # Detect protocol
    protocol = 'unknown'
    if data_bytes.startswith(b'omni'):
        protocol = 'omni'
    elif data_bytes.startswith(bytes.fromhex('0109f91102')):
        protocol = 'opentimestamps'
    
    return {
        'op_return_data_hex': data_hex,
        'op_return_data_utf8': data_utf8,
        'op_return_protocol': protocol
    }


def scriptpubkey_to_address(script_hex, network='mainnet'):
    """
    Convert scriptPubKey to address.
    
    Args:
        script_hex: str
        network: 'mainnet' or 'testnet'
    
    Returns:
        str (address) or None if not a recognized type
    """
    from .address import pubkey_hash_to_p2pkh_address, script_hash_to_p2sh_address, witness_program_to_address
    
    script_type = classify_output_script(script_hex)
    script = bytes.fromhex(script_hex)
    
    if script_type == 'p2pkh':
        # Extract 20-byte hash (bytes 3-23)
        pubkey_hash = script[3:23]
        return pubkey_hash_to_p2pkh_address(pubkey_hash, network)
    
    elif script_type == 'p2sh':
        # Extract 20-byte hash (bytes 2-22)
        script_hash = script[2:22]
        return script_hash_to_p2sh_address(script_hash, network)
    
    elif script_type == 'p2wpkh':
        # Witness v0, 20-byte program
        witprog = script[2:]
        return witness_program_to_address(0, witprog, network)
    
    elif script_type == 'p2wsh':
        # Witness v0, 32-byte program
        witprog = script[2:]
        return witness_program_to_address(0, witprog, network)
    
    elif script_type == 'p2tr':
        # Witness v1, 32-byte program
        witprog = script[2:]
        return witness_program_to_address(1, witprog, network)
    
    else:
        return None
