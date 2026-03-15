"""
Bitcoin CompactSize (varint) parser

Bitcoin uses a variable-length integer encoding called CompactSize:
- 0xFD followed by 2 bytes (little-endian uint16)
- 0xFE followed by 4 bytes (little-endian uint32)
- 0xFF followed by 8 bytes (little-endian uint64)
- Otherwise, the value itself (uint8)

Reference: https://developer.bitcoin.org/reference/transactions.html#compactsize-unsigned-integers
"""

import struct

# Sanity cap — no single Bitcoin entity (tx count, script length, etc.)
# should exceed this in valid chain data
MAX_VARINT = 4_000_000


def read_varint(data, offset=0):
    """
    Read a Bitcoin CompactSize varint following official specification.
    
    Official spec (https://developer.bitcoin.org/reference/transactions.html):
    Prefix   Meaning
    <253     value (1 byte)
    253      next 2 bytes (little-endian)
    254      next 4 bytes (little-endian) 
    255      next 8 bytes (little-endian)
    
    Args:
        data: bytes object
        offset: starting position
    
    Returns:
        (value, new_offset) tuple
    """
    if offset >= len(data):
        raise ValueError("Offset exceeds data length")
    
    first_byte = data[offset]
    
    if first_byte < 253:  # 0xFD
        # Single byte value
        return (first_byte, offset + 1)
    
    elif first_byte == 253:  # 0xFD
        # Next 2 bytes (little-endian)
        if offset + 3 > len(data):
            raise ValueError("Insufficient data for 0xFD varint")
        value = struct.unpack('<H', data[offset+1:offset+3])[0]
        # Bitcoin Core validation: must be >= 253
        if value < 253:
            raise ValueError(f"Non-canonical varint encoding: {value}")
        return (value, offset + 3)
    
    elif first_byte == 254:  # 0xFE
        # Next 4 bytes (little-endian)
        if offset + 5 > len(data):
            raise ValueError("Insufficient data for 0xFE varint")
        value = struct.unpack('<I', data[offset+1:offset+5])[0]
        # Bitcoin Core validation: must be >= 65536
        if value < 65536:
            raise ValueError(f"Non-canonical varint encoding: {value}")
        return (value, offset + 5)
    
    else:  # first_byte == 255 (0xFF)
        # Next 8 bytes (little-endian)
        if offset + 9 > len(data):
            raise ValueError("Insufficient data for 0xFF varint")
        value = struct.unpack('<Q', data[offset+1:offset+9])[0]
        # Bitcoin Core validation: must be >= 4294967296
        if value < 4294967296:
            raise ValueError(f"Non-canonical varint encoding: {value}")
        return (value, offset + 9)


def encode_varint(value):
    """
    Encode an integer as a Bitcoin CompactSize varint.
    
    Args:
        value: integer to encode
    
    Returns:
        bytes object
    """
    if value < 0:
        raise ValueError("Varint value must be non-negative")
    
    if value < 0xFD:
        return bytes([value])
    
    elif value <= 0xFFFF:
        return b'\xfd' + struct.pack('<H', value)
    
    elif value <= 0xFFFFFFFF:
        return b'\xfe' + struct.pack('<I', value)
    
    else:
        return b'\xff' + struct.pack('<Q', value)
