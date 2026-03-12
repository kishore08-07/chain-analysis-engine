"""
Merkle tree computation for Bitcoin blocks

Reference: https://developer.bitcoin.org/reference/block_chain.html#merkle-trees
"""

from .crypto import double_sha256


def compute_merkle_root(tx_hashes):
    """
    Compute Merkle root following official Bitcoin Core algorithm.
    
    Official spec (https://developer.bitcoin.org/reference/block_chain.html):
    1. hash1 = SHA256(SHA256(tx))
    2. pair hashes
    3. hash again  
    4. repeat until one root
    5. If odd number → duplicate last hash
    
    Args:
        tx_hashes: list of bytes (32-byte hashes, internal byte order)
    
    Returns:
        bytes (32-byte Merkle root, internal byte order)
    """
    if len(tx_hashes) == 0:
        # Empty list - return zero hash
        return b'\\x00' * 32
    
    if len(tx_hashes) == 1:
        return tx_hashes[0]
    
    # Build Merkle tree bottom-up following Bitcoin Core logic
    level = list(tx_hashes)
    
    while len(level) > 1:
        next_level = []
        
        # Process pairs - Bitcoin Core algorithm
        for i in range(0, len(level), 2):
            left = level[i]
            
            if i + 1 < len(level):
                right = level[i + 1]
            else:
                # Odd number of nodes - duplicate the last one (Bitcoin Core rule)
                right = left
            
            # Hash the pair: SHA256(SHA256(left + right))
            parent = double_sha256(left + right)
            next_level.append(parent)
        
        level = next_level
    
    return level[0]
