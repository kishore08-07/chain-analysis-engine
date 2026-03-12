"""
Cryptographic utilities for Bitcoin

Implements:
- SHA256 hashing
- RIPEMD160 hashing
- Double SHA256 (used for txid, block hash)
- Hash160 (SHA256 + RIPEMD160, used for addresses)

All use Python standard library (hashlib).
"""

import hashlib


def sha256(data):
    """
    Compute SHA256 hash of data.
    
    Args:
        data: bytes
    
    Returns:
        bytes (32 bytes)
    """
    return hashlib.sha256(data).digest()


def ripemd160(data):
    """
    Compute RIPEMD160 hash of data.
    
    Args:
        data: bytes
    
    Returns:
        bytes (20 bytes)
    """
    return hashlib.new('ripemd160', data).digest()


def double_sha256(data):
    """
    Compute double SHA256 hash (SHA256(SHA256(data))).
    Used for txid and block hash computation.
    
    Args:
        data: bytes
    
    Returns:
        bytes (32 bytes)
    """
    return sha256(sha256(data))


def hash160(data):
    """
    Compute Hash160 (RIPEMD160(SHA256(data))).
    Used for generating P2PKH and P2SH addresses.
    
    Args:
        data: bytes
    
    Returns:
        bytes (20 bytes)
    """
    return ripemd160(sha256(data))


def reverse_bytes(data):
    """
    Reverse byte order (used for Bitcoin's display convention).
    
    Bitcoin internally stores hashes in little-endian, but displays
    them in big-endian (reversed) for human readability.
    
    Args:
        data: bytes
    
    Returns:
        reversed bytes
    """
    return data[::-1]
