"""
Unit tests for core modules:
  - crypto.py
  - varint.py
  - merkle.py
  - address.py
  - script_parser.py
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.core.crypto import sha256, double_sha256, hash160, ripemd160, reverse_bytes
from src.core.varint import read_varint, encode_varint
from src.core.merkle import compute_merkle_root
from src.core.address import (
    base58_encode, base58_decode,
    base58check_encode, base58check_decode,
    pubkey_hash_to_p2pkh_address, script_hash_to_p2sh_address,
    witness_program_to_address,
)
from src.core.script_parser import (
    classify_output_script, disassemble_script,
    extract_op_return_data, scriptpubkey_to_address,
)


# ─── crypto ────────────────────────────────────────────────────────────────────

class TestCrypto:
    """Tests for cryptographic utilities."""

    def test_sha256_known_empty(self):
        """SHA256 of empty bytes matches known constant."""
        result = sha256(b'')
        expected = bytes.fromhex(
            'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
        )
        assert result == expected

    def test_sha256_known_abc(self):
        """sha256() wrapper produces same output as hashlib.sha256."""
        import hashlib as _hl
        data = b'abc'
        assert sha256(data) == _hl.sha256(data).digest()
        assert len(sha256(data)) == 32

    def test_double_sha256_returns_32_bytes(self):
        """Double SHA256 always returns 32 bytes."""
        result = double_sha256(b'hello')
        assert isinstance(result, bytes)
        assert len(result) == 32

    def test_double_sha256_differs_from_single(self):
        """Double SHA256 differs from single SHA256."""
        data = b'bitcoin'
        assert double_sha256(data) != sha256(data)

    def test_hash160_returns_20_bytes(self):
        """Hash160 (SHA256 + RIPEMD160) always returns 20 bytes."""
        result = hash160(b'pubkey_data')
        assert isinstance(result, bytes)
        assert len(result) == 20

    def test_reverse_bytes(self):
        """reverse_bytes reverses byte order."""
        data = bytes([0x01, 0x02, 0x03, 0x04])
        assert reverse_bytes(data) == bytes([0x04, 0x03, 0x02, 0x01])

    def test_reverse_bytes_involution(self):
        """Reversing twice returns original."""
        data = b'abcdefgh'
        assert reverse_bytes(reverse_bytes(data)) == data


# ─── varint ────────────────────────────────────────────────────────────────────

class TestVarint:
    """Tests for CompactSize varint parsing and encoding."""

    def test_read_single_byte(self):
        """Values < 253 are read as single bytes."""
        value, offset = read_varint(bytes([0x01]), 0)
        assert value == 1
        assert offset == 1

    def test_read_single_byte_max(self):
        """Value 252 is still a single byte."""
        value, offset = read_varint(bytes([0xfc]), 0)
        assert value == 252
        assert offset == 1

    def test_read_fd_prefix(self):
        """0xFD prefix reads next 2 bytes little-endian."""
        data = bytes([0xfd, 0x01, 0x01])  # 0x0101 = 257
        value, offset = read_varint(data, 0)
        assert value == 257
        assert offset == 3

    def test_read_fe_prefix(self):
        """0xFE prefix reads next 4 bytes little-endian."""
        # 0x00010000 = 65536
        data = bytes([0xfe, 0x00, 0x00, 0x01, 0x00])
        value, offset = read_varint(data, 0)
        assert value == 65536
        assert offset == 5

    def test_read_ff_prefix(self):
        """0xFF prefix reads next 8 bytes little-endian."""
        # 0x0000000100000000 = 4294967296
        data = bytes([0xff, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00])
        value, offset = read_varint(data, 0)
        assert value == 4294967296
        assert offset == 9

    def test_read_varint_with_offset(self):
        """read_varint respects the provided offset."""
        data = bytes([0x00, 0x05])
        value, new_offset = read_varint(data, 1)
        assert value == 5
        assert new_offset == 2

    def test_read_varint_insufficient_data_raises(self):
        """Insufficient data raises ValueError."""
        with pytest.raises(ValueError):
            read_varint(bytes([0xfd, 0x01]))  # Only 1 byte after 0xfd

    def test_read_varint_non_canonical_raises(self):
        """Non-canonical encoding raises ValueError."""
        # 0xFD prefix but value < 253 (e.g. 100)
        data = bytes([0xfd, 0x64, 0x00])  # 0x0064 = 100
        with pytest.raises(ValueError):
            read_varint(data, 0)

    def test_encode_varint_small(self):
        """Small values encode as single byte."""
        assert encode_varint(0) == bytes([0x00])
        assert encode_varint(252) == bytes([0xfc])

    def test_encode_varint_fd(self):
        """Values 253–65535 encode with 0xFD prefix."""
        result = encode_varint(253)
        assert result[0] == 0xfd
        assert len(result) == 3

    def test_encode_varint_fe(self):
        """Values 65536–4294967295 encode with 0xFE prefix."""
        result = encode_varint(65536)
        assert result[0] == 0xfe
        assert len(result) == 5

    def test_encode_varint_negative_raises(self):
        """Negative values raise ValueError."""
        with pytest.raises(ValueError):
            encode_varint(-1)

    def test_round_trip_varint(self):
        """Encode then decode yields the original value."""
        for v in [0, 1, 252, 253, 300, 65536, 100000]:
            encoded = encode_varint(v)
            decoded, _ = read_varint(encoded, 0)
            assert decoded == v, f"Round-trip failed for {v}"


# ─── merkle ────────────────────────────────────────────────────────────────────

class TestMerkle:
    """Tests for Merkle root computation."""

    def test_empty_list_returns_zero_hash(self):
        """Empty list → 32 zero bytes."""
        result = compute_merkle_root([])
        assert result == b'\x00' * 32

    def test_single_hash_returned_as_is(self):
        """Single hash is returned unchanged."""
        h = sha256(b'single')
        result = compute_merkle_root([h])
        assert result == h

    def test_two_hashes_yields_32_bytes(self):
        """Two hashes produce a valid 32-byte root."""
        h1 = sha256(b'tx1')
        h2 = sha256(b'tx2')
        result = compute_merkle_root([h1, h2])
        assert isinstance(result, bytes)
        assert len(result) == 32

    def test_even_count_deterministic(self):
        """Same hashes always produce same root (deterministic)."""
        hashes = [sha256(bytes([i])) for i in range(4)]
        r1 = compute_merkle_root(hashes)
        r2 = compute_merkle_root(hashes)
        assert r1 == r2

    def test_odd_count_duplicates_last(self):
        """Odd number of hashes: last is duplicated, root differs from even."""
        h1 = sha256(b'a')
        h2 = sha256(b'b')
        h3 = sha256(b'c')
        root_odd = compute_merkle_root([h1, h2, h3])
        # With duplication: [h1,h2,h3,h3] should give same as [h1,h2,h3,h3]
        root_dup = compute_merkle_root([h1, h2, h3, h3])
        assert root_odd == root_dup

    def test_order_matters(self):
        """Different ordering produces different root."""
        h1 = sha256(b'tx1')
        h2 = sha256(b'tx2')
        r1 = compute_merkle_root([h1, h2])
        r2 = compute_merkle_root([h2, h1])
        assert r1 != r2


# ─── address ───────────────────────────────────────────────────────────────────

class TestAddress:
    """Tests for Bitcoin address encoding / decoding."""

    def test_base58_roundtrip(self):
        """base58_encode then base58_decode recovers original bytes."""
        data = bytes(range(20))
        encoded = base58_encode(data)
        decoded = base58_decode(encoded)
        # base58_decode may add leading zero bytes — strip to compare
        assert decoded.lstrip(b'\x00') == data.lstrip(b'\x00')

    def test_base58check_encode_returns_string(self):
        """base58check_encode produces a non-empty string."""
        payload = b'\x00' * 20
        result = base58check_encode(0, payload)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_base58check_decode_roundtrip(self):
        """base58check encode → decode recovers version and payload."""
        payload = hash160(b'test_pubkey')
        addr = base58check_encode(0, payload)
        version, decoded_payload = base58check_decode(addr)
        assert version == 0
        assert decoded_payload == payload

    def test_base58check_invalid_checksum_raises(self):
        """Tampered address raises ValueError due to bad checksum."""
        payload = hash160(b'pubkey')
        addr = base58check_encode(0, payload)
        # Flip last character
        tampered = addr[:-1] + ('2' if addr[-1] != '2' else '3')
        with pytest.raises(ValueError):
            base58check_decode(tampered)

    def test_p2pkh_mainnet_address_prefix(self):
        """Mainnet P2PKH address starts with '1'."""
        pubkey_hash = hash160(b'compressed_pubkey')
        addr = pubkey_hash_to_p2pkh_address(pubkey_hash, network='mainnet')
        assert addr.startswith('1')

    def test_p2pkh_testnet_address_prefix(self):
        """Testnet P2PKH address starts with 'm' or 'n'."""
        pubkey_hash = hash160(b'compressed_pubkey')
        addr = pubkey_hash_to_p2pkh_address(pubkey_hash, network='testnet')
        assert addr[0] in ('m', 'n')

    def test_p2sh_mainnet_address_prefix(self):
        """Mainnet P2SH address starts with '3'."""
        script_hash = hash160(b'redeem_script')
        addr = script_hash_to_p2sh_address(script_hash, network='mainnet')
        assert addr.startswith('3')

    def test_p2wpkh_address_bech32(self):
        """P2WPKH produces a valid bech32 'bc1q' address."""
        witprog = hash160(b'compressed_pubkey')[:20]  # 20 bytes
        addr = witness_program_to_address(0, witprog, network='mainnet')
        assert addr.startswith('bc1q')

    def test_p2tr_address_bech32m(self):
        """P2TR (witness version 1) produces a 'bc1p' bech32m address."""
        witprog = sha256(b'x_only_pubkey')  # 32 bytes
        addr = witness_program_to_address(1, witprog, network='mainnet')
        assert addr.startswith('bc1p')


# ─── script_parser ─────────────────────────────────────────────────────────────

class TestScriptParser:
    """Tests for script classification and disassembly."""

    # P2PKH: OP_DUP OP_HASH160 <20 bytes> OP_EQUALVERIFY OP_CHECKSIG
    P2PKH = '76a914' + '00' * 20 + '88ac'
    # P2SH: OP_HASH160 <20 bytes> OP_EQUAL
    P2SH = 'a914' + 'ff' * 20 + '87'
    # P2WPKH: OP_0 <20 bytes>
    P2WPKH = '0014' + 'ab' * 20
    # P2WSH: OP_0 <32 bytes>
    P2WSH = '0020' + 'cd' * 32
    # P2TR: OP_1 <32 bytes>
    P2TR = '5120' + 'ef' * 32
    # OP_RETURN
    OP_RETURN = '6a04deadbeef'

    def test_classify_p2pkh(self):
        assert classify_output_script(self.P2PKH) == 'p2pkh'

    def test_classify_p2sh(self):
        assert classify_output_script(self.P2SH) == 'p2sh'

    def test_classify_p2wpkh(self):
        assert classify_output_script(self.P2WPKH) == 'p2wpkh'

    def test_classify_p2wsh(self):
        assert classify_output_script(self.P2WSH) == 'p2wsh'

    def test_classify_p2tr(self):
        assert classify_output_script(self.P2TR) == 'p2tr'

    def test_classify_op_return(self):
        assert classify_output_script(self.OP_RETURN) == 'op_return'

    def test_classify_unknown(self):
        """Random data that doesn't match any pattern → 'unknown'."""
        result = classify_output_script('deadbeef0102030405')
        assert result == 'unknown'

    def test_disassemble_empty(self):
        """Empty script → empty string."""
        assert disassemble_script('') == ''

    def test_disassemble_op_return(self):
        """OP_RETURN appears in disassembly."""
        asm = disassemble_script(self.OP_RETURN)
        assert 'OP_RETURN' in asm

    def test_extract_op_return_data_has_hex(self):
        """extract_op_return_data returns op_return_data_hex key."""
        result = extract_op_return_data(self.OP_RETURN)
        assert 'op_return_data_hex' in result

    def test_p2pkh_scriptpubkey_to_address(self):
        """P2PKH script converts to a mainnet address starting with '1'."""
        addr = scriptpubkey_to_address(self.P2PKH, 'mainnet')
        assert addr is not None
        assert addr.startswith('1')

    def test_p2wpkh_scriptpubkey_to_address(self):
        """P2WPKH script converts to a bech32 address."""
        addr = scriptpubkey_to_address(self.P2WPKH, 'mainnet')
        assert addr is not None
        assert addr.startswith('bc1')
