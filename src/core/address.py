"""
Bitcoin address encoding and decoding

Implements:
- Base58Check encoding/decoding (P2PKH, P2SH)
- Bech32 encoding (P2WPKH, P2WSH) per BIP173
- Bech32m encoding (P2TR) per BIP341

References:
- Base58Check: https://en.bitcoin.it/wiki/Base58Check_encoding
- BIP173 (Bech32): https://github.com/bitcoin/bips/blob/master/bip-0173.mediawiki
- BIP341 (Taproot/Bech32m): https://github.com/bitcoin/bips/blob/master/bip-0341.mediawiki
"""

from .crypto import sha256, double_sha256


# Base58 alphabet (no 0, O, I, l to avoid confusion)
BASE58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'


def base58_encode(data):
    """
    Encode bytes to Base58.
    
    Args:
        data: bytes
    
    Returns:
        str
    """
    # Convert bytes to integer
    num = int.from_bytes(data, 'big')
    
    # Encode to base58
    encoded = ''
    while num > 0:
        num, remainder = divmod(num, 58)
        encoded = BASE58_ALPHABET[remainder] + encoded
    
    # Preserve leading zero bytes as '1'
    for byte in data:
        if byte == 0:
            encoded = '1' + encoded
        else:
            break
    
    return encoded


def base58_decode(s):
    """
    Decode Base58 string to bytes.
    
    Args:
        s: Base58 string
    
    Returns:
        bytes
    """
    num = 0
    for char in s:
        num = num * 58 + BASE58_ALPHABET.index(char)
    
    # Convert to bytes
    combined = num.to_bytes((num.bit_length() + 7) // 8, 'big')
    
    # Add leading zero bytes for each leading '1'
    for char in s:
        if char == '1':
            combined = b'\x00' + combined
        else:
            break
    
    return combined


def base58check_encode(version, payload):
    """
    Encode data with Base58Check (with version byte and checksum).
    
    Args:
        version: int (version byte, e.g., 0 for P2PKH mainnet)
        payload: bytes (e.g., 20-byte hash)
    
    Returns:
        str (Base58Check encoded address)
    """
    # Combine version + payload
    versioned = bytes([version]) + payload
    
    # Compute checksum (first 4 bytes of double SHA256)
    checksum = double_sha256(versioned)[:4]
    
    # Encode version + payload + checksum
    return base58_encode(versioned + checksum)


def base58check_decode(address):
    """
    Decode Base58Check address.
    
    Args:
        address: str
    
    Returns:
        (version, payload) tuple
    
    Raises:
        ValueError if checksum is invalid
    """
    decoded = base58_decode(address)
    
    # Split into version, payload, and checksum
    version = decoded[0]
    payload = decoded[1:-4]
    checksum = decoded[-4:]
    
    # Verify checksum
    expected_checksum = double_sha256(decoded[:-4])[:4]
    if checksum != expected_checksum:
        raise ValueError("Invalid Base58Check checksum")
    
    return (version, payload)


# Bech32 character set
BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def bech32_polymod(values):
    """Bech32 checksum polymod computation."""
    GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
    chk = 1
    for value in values:
        b = chk >> 25
        chk = (chk & 0x1ffffff) << 5 ^ value
        for i in range(5):
            chk ^= GEN[i] if ((b >> i) & 1) else 0
    return chk


def bech32_hrp_expand(hrp):
    """Expand HRP for Bech32 checksum."""
    return [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]


def bech32_verify_checksum(hrp, data, const):
    """Verify Bech32/Bech32m checksum."""
    return bech32_polymod(bech32_hrp_expand(hrp) + data) == const


def bech32_create_checksum(hrp, data, const):
    """Create Bech32/Bech32m checksum."""
    values = bech32_hrp_expand(hrp) + data
    polymod = bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ const
    return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]


def bech32_encode(hrp, witver, witprog, spec):
    """
    Encode SegWit address using Bech32 or Bech32m.
    
    Args:
        hrp: str (human-readable part, e.g., "bc" for mainnet)
        witver: int (witness version, 0-16)
        witprog: bytes (witness program)
        spec: "bech32" or "bech32m"
    
    Returns:
        str (Bech32/Bech32m encoded address)
    """
    # Convert 8-bit witness program to 5-bit groups
    data = convertbits(witprog, 8, 5)
    if data is None:
        return None
    
    # Prepend witness version
    data = [witver] + data
    
    # Create checksum
    const = 1 if spec == "bech32" else 0x2bc830a3  # Bech32m constant
    checksum = bech32_create_checksum(hrp, data, const)
    
    # Encode to Bech32
    combined = data + checksum
    return hrp + '1' + ''.join([BECH32_CHARSET[d] for d in combined])


def bech32_decode(addr):
    """
    Decode Bech32/Bech32m address.
    
    Returns:
        (hrp, witver, witprog, spec) or (None, None, None, None) if invalid
    """
    # Find separator
    pos = addr.rfind('1')
    if pos < 1 or pos + 7 > len(addr) or len(addr) > 90:
        return (None, None, None, None)
    
    # Split HRP and data
    hrp = addr[:pos].lower()
    data_part = addr[pos+1:].lower()
    
    # Decode data
    data = []
    for c in data_part:
        if c not in BECH32_CHARSET:
            return (None, None, None, None)
        data.append(BECH32_CHARSET.index(c))
    
    # Verify checksum (try both Bech32 and Bech32m)
    spec = None
    if bech32_verify_checksum(hrp, data, 1):
        spec = "bech32"
    elif bech32_verify_checksum(hrp, data, 0x2bc830a3):
        spec = "bech32m"
    else:
        return (None, None, None, None)
    
    # Extract witness version and program
    data = data[:-6]  # Remove checksum
    if len(data) < 1:
        return (None, None, None, None)
    
    witver = data[0]
    witprog = convertbits(data[1:], 5, 8, False)
    
    if witprog is None or len(witprog) < 2 or len(witprog) > 40:
        return (None, None, None, None)
    
    # Witness v0 uses Bech32, v1+ uses Bech32m
    if witver == 0 and spec != "bech32":
        return (None, None, None, None)
    if witver >= 1 and spec != "bech32m":
        return (None, None, None, None)
    
    return (hrp, witver, witprog, spec)


def convertbits(data, frombits, tobits, pad=True):
    """Convert between bit groups."""
    acc = 0
    bits = 0
    ret = []
    maxv = (1 << tobits) - 1
    max_acc = (1 << (frombits + tobits - 1)) - 1
    for value in data:
        if value < 0 or (value >> frombits):
            return None
        acc = ((acc << frombits) | value) & max_acc
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        return None
    return ret


def pubkey_hash_to_p2pkh_address(pubkey_hash, network='mainnet'):
    """
    Convert 20-byte pubkey hash to P2PKH address.
    
    Args:
        pubkey_hash: bytes (20 bytes, Hash160 of public key)
        network: 'mainnet' or 'testnet'
    
    Returns:
        str (P2PKH address)
    """
    version = 0 if network == 'mainnet' else 111
    return base58check_encode(version, pubkey_hash)


def script_hash_to_p2sh_address(script_hash, network='mainnet'):
    """
    Convert 20-byte script hash to P2SH address.
    
    Args:
        script_hash: bytes (20 bytes, Hash160 of redeem script)
        network: 'mainnet' or 'testnet'
    
    Returns:
        str (P2SH address)
    """
    version = 5 if network == 'mainnet' else 196
    return base58check_encode(version, script_hash)


def witness_program_to_address(witver, witprog, network='mainnet'):
    """
    Convert witness version and program to SegWit address.
    
    Args:
        witver: int (witness version, 0-16)
        witprog: bytes (witness program)
        network: 'mainnet' or 'testnet'
    
    Returns:
        str (Bech32/Bech32m address)
    """
    hrp = 'bc' if network == 'mainnet' else 'tb'
    
    # Witness v0 uses Bech32, v1+ uses Bech32m
    spec = "bech32" if witver == 0 else "bech32m"
    
    return bech32_encode(hrp, witver, witprog, spec)
