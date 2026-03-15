"""
Bitcoin Core undo file (rev*.dat) parser

Implements Bitcoin Core's exact undo data parsing following undo.h and compressor.cpp.

Format of rev*.dat:
- For each block: network_magic(4) + block_size(4) + CBlockUndo + checksum(32)
- CBlockUndo: CompactSize(num_non_coinbase_txs) + [CTxUndo...]
- CTxUndo: CompactSize(num_inputs) + [CTxInUndo...]
- CTxInUndo: nCode(varint) + compressed_CTxOut

nCode (per undo.h):
- Encodes (nHeight * 4) | (fCoinBase << 1) | (fHasUncompressedPrevout)
- We only need the compressed CTxOut that follows

Compressed CTxOut (per compressor.cpp):
- Compressed amount (custom varint encoding)
- Compressed script:
  - nSize=0: P2PKH (20-byte hash follows)
  - nSize=1: P2SH (20-byte hash follows)
  - nSize=2,3: Compressed P2PK (32 bytes follow)
  - nSize=4,5: Uncompressed P2PK (32 bytes follow)
  - nSize>=6: Raw script (nSize-6 bytes follow)

References:
- https://github.com/bitcoin/bitcoin/blob/master/src/undo.h
- https://github.com/bitcoin/bitcoin/blob/master/src/compressor.h
- https://github.com/bitcoin/bitcoin/blob/master/src/compressor.cpp
"""

import struct
from .varint import read_varint


MAINNET_MAGIC = b'\xf9\xbe\xb4\xd9'
TESTNET_MAGIC = b'\x0b\x11\x09\x07'


def read_core_varint(data, offset):
    """
    Read Bitcoin Core's VARINT encoding (serialize.h WriteVARINT/ReadVARINT).

    This is DIFFERENT from CompactSize. Bitcoin Core uses this for
    nCode, compressed amounts, and nSize in undo data.

    Algorithm (from serialize.h):
      n = 0
      loop:
        chData = next byte
        if chData < 0x80:   # no continuation
          return n | chData
        n = (n | (chData & 0x7f)) + 1
        n <<= 7

    Returns:
        (value, new_offset)
    """
    n = 0
    while True:
        if offset >= len(data):
            raise ValueError("Unexpected end of data in VARINT")
        ch = data[offset]
        offset += 1
        if ch < 0x80:
            return (n | ch, offset)
        n = (n | (ch & 0x7f)) + 1
        n <<= 7


def parse_undo_file(undo_file_path, xor_file_path=None):
    """
    Parse Bitcoin Core undo file (rev*.dat).

    The undo file has the same container format as blk*.dat:
      magic(4) + size(4) + payload + sha256d_checksum(32)

    Each payload is a CBlockUndo for one block, in the same order as
    the blocks appear in the corresponding blk*.dat.

    Returns:
        list of block_undos, where each block_undo is a list of tx_undos,
        and each tx_undo is a list of prevout dicts.

    Raises:
        ValueError: if undo data is corrupted
    """
    with open(undo_file_path, 'rb') as f:
        data = f.read()

    # Apply XOR decryption if key provided
    xor_key = b''
    if xor_file_path:
        try:
            with open(xor_file_path, 'rb') as f:
                xor_key = f.read()
        except Exception:
            pass

    if xor_key and any(b != 0 for b in xor_key):
        data = apply_xor_decryption(data, xor_key)

    return parse_undo_blocks(data)


def apply_xor_decryption(data, xor_key):
    """
    Apply XOR decryption using Bitcoin Core's obfuscation method.

    Uses big-integer XOR for O(1) bitwise operations — much faster than
    byte-by-byte iteration for large undo files.
    """
    if not xor_key:
        return data
    data_len = len(data)
    if data_len == 0:
        return data
    key_len = len(xor_key)
    repeats = (data_len // key_len) + 1
    full_key = (xor_key * repeats)[:data_len]
    data_int = int.from_bytes(data, 'big')
    key_int = int.from_bytes(full_key, 'big')
    return (data_int ^ key_int).to_bytes(data_len, 'big')


def parse_undo_blocks(data):
    """
    Parse all CBlockUndo records from the undo file.

    Bitcoin Core rev*.dat container format per block:
      magic(4) + size(4) + CBlockUndo_data(size bytes) + sha256d_checksum(32)

    The size field does NOT include the 32-byte checksum, so we must
    skip an extra 32 bytes after each payload.

    Returns:
        list of dicts, each with:
          - 'num_txs': number of non-coinbase transactions
          - 'tx_undos': list of tx_undos (each a list of prevout dicts)
          - 'raw_bytes': raw CBlockUndo serialized bytes (for checksum verification)
          - 'checksum': 32-byte sha256d checksum from the file
    """
    block_undos = []
    offset = 0

    while offset < len(data):
        # Check for magic bytes
        if offset + 8 > len(data):
            break

        magic = data[offset:offset + 4]
        if magic != MAINNET_MAGIC and magic != TESTNET_MAGIC:
            break

        offset += 4

        # Block undo size (4 bytes LE) — does NOT include the 32-byte checksum
        block_undo_size = struct.unpack('<I', data[offset:offset + 4])[0]
        offset += 4

        if block_undo_size == 0 or offset + block_undo_size > len(data):
            break

        # Save raw undo bytes for checksum verification
        undo_raw = data[offset:offset + block_undo_size]

        # Parse CBlockUndo from the payload
        try:
            block_undo, _ = parse_single_block_undo(data, offset)
        except Exception as e:
            raise ValueError(f"Failed to parse block undo at offset {offset}: {e}")

        # Read 32-byte checksum after undo data
        checksum_offset = offset + block_undo_size
        checksum = None
        if checksum_offset + 32 <= len(data):
            checksum = data[checksum_offset:checksum_offset + 32]

        block_undos.append({
            'num_txs': len(block_undo),
            'tx_undos': block_undo,
            'raw_bytes': undo_raw,
            'checksum': checksum
        })

        # Advance past undo data + 32-byte checksum
        offset = checksum_offset + 32

    return block_undos


def parse_single_block_undo(data, offset):
    """
    Parse a single CBlockUndo.

    CBlockUndo format (undo.h):
      CompactSize(nTxs)  -- number of non-coinbase transactions
      For each tx:
        CTxUndo

    Returns:
        (block_undo, new_offset) where block_undo is a list of tx_undos
    """
    num_txs, offset = read_varint(data, offset)

    if num_txs > 500000:
        raise ValueError(f"Unreasonable tx count in undo: {num_txs}")

    block_undo = []
    for _ in range(num_txs):
        tx_undo, offset = parse_tx_undo(data, offset)
        block_undo.append(tx_undo)

    return block_undo, offset


def parse_tx_undo(data, offset):
    """
    Parse a CTxUndo for one transaction.

    CTxUndo format (undo.h):
      CompactSize(nInputs)
      For each input: CTxInUndo

    Returns:
        (tx_undo, new_offset) where tx_undo is a list of prevout dicts
    """
    num_inputs, offset = read_varint(data, offset)

    if num_inputs > 100000:
        raise ValueError(f"Unreasonable input count in undo: {num_inputs}")

    prevouts = []
    for _ in range(num_inputs):
        prevout, offset = parse_txin_undo(data, offset)
        prevouts.append(prevout)

    return prevouts, offset


def parse_txin_undo(data, offset):
    """
    Parse a CTxInUndo (one spent input's prevout data).

    Per Bitcoin Core undo.h TxInUndoFormatter::Unser():
      1. nCode (VARINT): encodes nHeight * 2 + fCoinBase
      2. If nHeight > 0: nVersionDummy (VARINT) — legacy compat, read and discard
      3. Compressed CTxOut via TxOutCompression:
         - compressed_amount (VARINT)
         - compressed_script (VARINT nSize + script data)

    Returns:
        (prevout_dict, new_offset)
    """
    # Read nCode (VARINT)
    ncode, offset = read_core_varint(data, offset)
    nHeight = ncode >> 1
    # fCoinBase = ncode & 1

    # If nHeight > 0, read and discard the legacy version dummy
    if nHeight > 0:
        _version_dummy, offset = read_core_varint(data, offset)

    # Read compressed amount (VARINT)
    compressed_amount, offset = read_core_varint(data, offset)
    amount = decompress_amount(compressed_amount)

    # Read compressed script (nSize is VARINT)
    script_hex, offset = decompress_script(data, offset)

    return {
        'value_sats': amount,
        'script_pubkey_hex': script_hex
    }, offset


def decompress_amount(x):
    """
    Decompress amount from Bitcoin Core's compressed format.

    Reference: Bitcoin Core compressor.cpp DecompressAmount()
    """
    if x == 0:
        return 0
    x -= 1
    e = x % 10
    x //= 10
    if e < 9:
        d = (x % 9) + 1
        x //= 9
        n = x * 10 + d
    else:
        n = x + 1
    while e > 0:
        n *= 10
        e -= 1
    return n


def decompress_script(data, offset):
    """
    Decompress scriptPubKey from Bitcoin Core's compressed format.

    Reference: Bitcoin Core compressor.cpp DecompressScript()

    nSize encoding:
      0: P2PKH (20-byte hash follows)
      1: P2SH  (20-byte hash follows)
      2,3: Compressed P2PK (32-byte X coordinate follows)
      4,5: Uncompressed P2PK (32-byte X coordinate follows)
      >=6: Raw script (nSize-6 bytes follow)

    Returns:
        (script_hex, new_offset)
    """
    nSize, offset = read_core_varint(data, offset)

    if nSize == 0:
        # P2PKH: OP_DUP OP_HASH160 OP_PUSHBYTES_20 <20> OP_EQUALVERIFY OP_CHECKSIG
        if offset + 20 > len(data):
            raise ValueError("Insufficient data for P2PKH in undo")
        pubkey_hash = data[offset:offset + 20]
        offset += 20
        script = bytes([0x76, 0xa9, 0x14]) + pubkey_hash + bytes([0x88, 0xac])
        return script.hex(), offset

    elif nSize == 1:
        # P2SH: OP_HASH160 OP_PUSHBYTES_20 <20> OP_EQUAL
        if offset + 20 > len(data):
            raise ValueError("Insufficient data for P2SH in undo")
        script_hash = data[offset:offset + 20]
        offset += 20
        script = bytes([0xa9, 0x14]) + script_hash + bytes([0x87])
        return script.hex(), offset

    elif nSize in (2, 3):
        # Compressed P2PK: PUSH33 <compressed-pubkey> OP_CHECKSIG
        if offset + 32 > len(data):
            raise ValueError("Insufficient data for compressed P2PK in undo")
        x_coord = data[offset:offset + 32]
        offset += 32
        prefix = bytes([0x02 if nSize == 2 else 0x03])
        pubkey = prefix + x_coord
        script = bytes([0x21]) + pubkey + bytes([0xac])
        return script.hex(), offset

    elif nSize in (4, 5):
        # Uncompressed P2PK: store as compressed form for classification
        # Bitcoin Core stores only X coordinate; full Y recovery requires
        # elliptic curve computation. For classification the compressed
        # form is sufficient since we classify by script template.
        if offset + 32 > len(data):
            raise ValueError("Insufficient data for uncompressed P2PK in undo")
        x_coord = data[offset:offset + 32]
        offset += 32
        prefix = bytes([0x02 if nSize == 4 else 0x03])
        pubkey = prefix + x_coord
        script = bytes([0x21]) + pubkey + bytes([0xac])
        return script.hex(), offset

    else:
        # nSize >= 6: Raw script, length = nSize - 6
        script_len = nSize - 6
        if script_len > 100000:
            raise ValueError(f"Unreasonable raw script length: {script_len}")
        if offset + script_len > len(data):
            raise ValueError(f"Insufficient data for raw script (need {script_len} bytes)")
        script = data[offset:offset + script_len]
        offset += script_len
        return script.hex(), offset
