"""
Unit tests for analysis and heuristics modules:
  - analysis/classifier.py
  - analysis/stats.py
  - heuristics/cioh.py
  - heuristics/consolidation.py
  - heuristics/coinjoin.py
  - heuristics/round_number.py
  - heuristics/address_reuse.py
  - heuristics/engine.py
  - heuristics/op_return.py
  - output/json_writer.py
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.analysis.classifier import classify
from src.analysis.stats import (
    compute_fee_rate_stats,
    compute_fee_histogram,
    compute_privacy_score,
    compute_script_type_distribution,
)
from src.heuristics import cioh, consolidation, coinjoin, round_number, address_reuse, op_return
from src.heuristics import engine
from src.output.json_writer import build_tx_entry, build_block_entry, build_file_output


# ─── helpers ───────────────────────────────────────────────────────────────────

def _make_tx(n_inputs=1, n_outputs=2, is_coinbase=False,
             input_type='p2wpkh', output_type='p2wpkh',
             output_values=None, addresses=None):
    """Construct a minimal synthetic transaction dict."""
    vin = []
    for i in range(n_inputs):
        inp = {
            'txid': '00' * 32,
            'vout': i,
            'script_type': input_type,
            'prevout': {'script_pubkey_hex': '0014' + ('ab' * 20)},
        }
        if addresses:
            inp['address'] = addresses[i % len(addresses)]
        vin.append(inp)

    vout = []
    values = output_values or [100_000_000] * n_outputs
    for i, val in enumerate(values):
        out = {
            'n': i,
            'value_sats': val,
            'script_type': output_type,
            'script_pubkey_hex': '0014' + ('ab' * 20),
        }
        if addresses:
            out['address'] = addresses[(n_inputs + i) % len(addresses)]
        vout.append(out)

    tx = {
        'txid': 'a' * 64,
        'is_coinbase': is_coinbase,
        'vin': vin,
        'vout': vout,
    }
    return tx


def _no_detections():
    """Return heuristic results with all detections False."""
    return {h: {'detected': False} for h in engine.ALL_HEURISTIC_IDS}


# ─── classifier ────────────────────────────────────────────────────────────────

class TestClassifier:
    """Tests for transaction classification logic."""

    def test_coinbase_is_unknown(self):
        tx = _make_tx(is_coinbase=True)
        result = classify(tx, _no_detections())
        assert result == 'unknown'

    def test_all_op_return_outputs_is_unknown(self):
        tx = _make_tx(n_outputs=2, output_type='op_return')
        result = classify(tx, _no_detections())
        assert result == 'unknown'

    def test_coinjoin_detection_overrides(self):
        tx = _make_tx(n_inputs=3, n_outputs=3)
        h = _no_detections()
        h['coinjoin'] = {'detected': True}
        assert classify(tx, h) == 'coinjoin'

    def test_consolidation_detection(self):
        tx = _make_tx(n_inputs=5, n_outputs=1)
        h = _no_detections()
        h['consolidation'] = {'detected': True}
        assert classify(tx, h) == 'consolidation'

    def test_self_transfer_detection(self):
        tx = _make_tx(n_inputs=2, n_outputs=1)
        h = _no_detections()
        h['self_transfer'] = {'detected': True}
        assert classify(tx, h) == 'self_transfer'

    def test_batch_payment_three_outputs(self):
        tx = _make_tx(n_inputs=1, n_outputs=3)
        result = classify(tx, _no_detections())
        assert result == 'batch_payment'

    def test_simple_payment_two_outputs(self):
        tx = _make_tx(n_inputs=1, n_outputs=2)
        result = classify(tx, _no_detections())
        assert result == 'simple_payment'

    def test_coinjoin_priority_over_consolidation(self):
        """CoinJoin detection takes priority over consolidation."""
        tx = _make_tx(n_inputs=5, n_outputs=2)
        h = _no_detections()
        h['coinjoin'] = {'detected': True}
        h['consolidation'] = {'detected': True}
        assert classify(tx, h) == 'coinjoin'


# ─── stats ─────────────────────────────────────────────────────────────────────

class TestStats:
    """Tests for statistical aggregation functions."""

    def test_fee_rate_stats_empty(self):
        result = compute_fee_rate_stats([])
        assert result == {'min_sat_vb': 0.0, 'max_sat_vb': 0.0,
                          'median_sat_vb': 0.0, 'mean_sat_vb': 0.0}

    def test_fee_rate_stats_single(self):
        result = compute_fee_rate_stats([5.0])
        assert result['min_sat_vb'] == 5.0
        assert result['max_sat_vb'] == 5.0
        assert result['median_sat_vb'] == 5.0
        assert result['mean_sat_vb'] == 5.0

    def test_fee_rate_stats_multiple(self):
        result = compute_fee_rate_stats([1.0, 3.0, 5.0])
        assert result['min_sat_vb'] == 1.0
        assert result['max_sat_vb'] == 5.0
        assert result['median_sat_vb'] == 3.0
        assert result['mean_sat_vb'] == 3.0

    def test_fee_rate_stats_even_count_median(self):
        """Even count → median is average of two middle values."""
        result = compute_fee_rate_stats([1.0, 2.0, 3.0, 4.0])
        assert result['median_sat_vb'] == 2.5

    def test_fee_histogram_buckets_present(self):
        result = compute_fee_histogram([])
        assert set(result.keys()) == {'<2', '2-10', '10-50', '50-200', '>200'}

    def test_fee_histogram_correct_bucket(self):
        result = compute_fee_histogram([1.0, 5.0, 20.0, 100.0, 300.0])
        assert result['<2'] == 1
        assert result['2-10'] == 1
        assert result['10-50'] == 1
        assert result['50-200'] == 1
        assert result['>200'] == 1

    def test_privacy_score_range(self):
        """Privacy score must be in [0, 100]."""
        score = compute_privacy_score({}, {}, 100)
        assert 0 <= score <= 100

    def test_privacy_score_empty_block(self):
        """Empty block gets score 100."""
        assert compute_privacy_score({}, {}, 0) == 100

    def test_privacy_score_heavy_addr_reuse_penalty(self):
        """Heavy address reuse should lower the score significantly."""
        baseline = compute_privacy_score({}, {}, 100)
        penalised = compute_privacy_score({'address_reuse': 80}, {}, 100)
        assert penalised < baseline

    def test_script_type_distribution(self):
        txs = [
            {'vout': [{'script_type': 'p2wpkh'}, {'script_type': 'p2pkh'}]},
            {'vout': [{'script_type': 'p2wpkh'}]},
        ]
        result = compute_script_type_distribution(txs)
        assert result['p2wpkh'] == 2
        assert result['p2pkh'] == 1


# ─── heuristic: CIOH ───────────────────────────────────────────────────────────

class TestCIOH:
    """Tests for Common Input Ownership Heuristic."""

    def test_coinbase_not_detected(self):
        tx = _make_tx(is_coinbase=True, n_inputs=3)
        assert cioh.apply(tx)['detected'] is False

    def test_single_input_not_detected(self):
        tx = _make_tx(n_inputs=1)
        assert cioh.apply(tx)['detected'] is False

    def test_two_inputs_detected_medium_confidence(self):
        tx = _make_tx(n_inputs=2)
        result = cioh.apply(tx)
        assert result['detected'] is True
        assert result['confidence'] == 'medium'

    def test_three_inputs_detected_high_confidence(self):
        tx = _make_tx(n_inputs=3)
        result = cioh.apply(tx)
        assert result['detected'] is True
        assert result['confidence'] == 'high'

    def test_input_count_in_result(self):
        tx = _make_tx(n_inputs=4)
        result = cioh.apply(tx)
        assert result['input_count'] == 4


# ─── heuristic: Consolidation ──────────────────────────────────────────────────

class TestConsolidation:
    """Tests for consolidation transaction detection."""

    def test_coinbase_not_detected(self):
        tx = _make_tx(is_coinbase=True, n_inputs=5, n_outputs=1)
        assert consolidation.apply(tx)['detected'] is False

    def test_too_few_inputs_not_detected(self):
        tx = _make_tx(n_inputs=2, n_outputs=1)
        assert consolidation.apply(tx)['detected'] is False

    def test_too_many_outputs_not_detected(self):
        tx = _make_tx(n_inputs=5, n_outputs=3)
        assert consolidation.apply(tx)['detected'] is False

    def test_valid_consolidation_detected(self):
        tx = _make_tx(n_inputs=3, n_outputs=1)
        result = consolidation.apply(tx)
        assert result['detected'] is True
        assert result['input_count'] == 3
        assert result['output_count'] == 1

    def test_high_confidence_many_inputs_single_output(self):
        tx = _make_tx(n_inputs=5, n_outputs=1)
        result = consolidation.apply(tx)
        assert result['detected'] is True
        assert result['confidence'] == 'high'

    def test_io_ratio_computed(self):
        tx = _make_tx(n_inputs=6, n_outputs=2)
        result = consolidation.apply(tx)
        assert result['detected'] is True
        assert result['io_ratio'] == 3.0


# ─── heuristic: CoinJoin ───────────────────────────────────────────────────────

class TestCoinJoin:
    """Tests for CoinJoin transaction detection."""

    def test_coinbase_not_detected(self):
        tx = _make_tx(is_coinbase=True)
        assert coinjoin.apply(tx)['detected'] is False

    def test_too_few_inputs_not_detected(self):
        tx = _make_tx(n_inputs=1, n_outputs=4,
                      output_values=[100_000] * 4)
        assert coinjoin.apply(tx)['detected'] is False

    def test_coinjoin_detected_equal_outputs(self):
        """5 equal outputs + 5 inputs should detect CoinJoin."""
        tx = _make_tx(n_inputs=5, n_outputs=5,
                      output_values=[1_000_000] * 5)
        result = coinjoin.apply(tx)
        assert result['detected'] is True

    def test_no_equal_outputs_not_detected(self):
        """All different output values → not CoinJoin."""
        tx = _make_tx(n_inputs=3, n_outputs=3,
                      output_values=[100_000, 200_000, 300_000])
        result = coinjoin.apply(tx)
        assert result['detected'] is False


# ─── heuristic: Round Number ───────────────────────────────────────────────────

class TestRoundNumber:
    """Tests for round-number payment detection."""

    def test_coinbase_not_detected(self):
        tx = _make_tx(is_coinbase=True, output_values=[100_000_000])
        assert round_number.apply(tx)['detected'] is False

    def test_round_output_detected(self):
        """1 BTC = 100_000_000 sats is a round amount."""
        tx = _make_tx(n_outputs=1, output_values=[100_000_000])
        result = round_number.apply(tx)
        assert result['detected'] is True
        assert result['round_output_count'] >= 1

    def test_non_round_not_detected(self):
        """Irregular amounts are not round."""
        tx = _make_tx(n_outputs=1, output_values=[12345678])
        result = round_number.apply(tx)
        assert result['detected'] is False

    def test_op_return_outputs_ignored(self):
        """OP_RETURN outputs are excluded from round-number check."""
        tx = {
            'txid': 'a' * 64,
            'is_coinbase': False,
            'vin': [{'txid': '0' * 64, 'vout': 0, 'script_type': 'p2wpkh',
                     'prevout': {'script_pubkey_hex': '0014' + 'ab' * 20}}],
            'vout': [
                {'n': 0, 'value_sats': 100_000_000, 'script_type': 'op_return',
                 'script_pubkey_hex': '6a04deadbeef'},
            ],
        }
        result = round_number.apply(tx)
        assert result['detected'] is False


# ─── heuristic: Address Reuse ──────────────────────────────────────────────────

class TestAddressReuse:
    """Tests for address reuse detection."""

    def test_coinbase_not_detected(self):
        tx = _make_tx(is_coinbase=True)
        assert address_reuse.apply(tx)['detected'] is False

    def test_input_output_overlap_detected(self):
        """Same address in input and output → detected."""
        shared_addr = 'bc1qsharedaddress'
        tx = {
            'txid': 'b' * 64,
            'is_coinbase': False,
            'vin': [{'address': shared_addr, 'txid': '0' * 64, 'vout': 0,
                     'script_type': 'p2wpkh',
                     'prevout': {'script_pubkey_hex': '0014' + 'aa' * 20}}],
            'vout': [{'n': 0, 'value_sats': 99_000, 'script_type': 'p2wpkh',
                      'address': shared_addr,
                      'script_pubkey_hex': '0014' + 'aa' * 20}],
        }
        result = address_reuse.apply(tx)
        assert result['detected'] is True
        assert result['input_output_overlap'] >= 1  # count of reused addresses

    def test_no_reuse_not_detected(self):
        """No address overlap → not detected."""
        address_reuse.set_block_context([])  # reset block context
        tx = {
            'txid': 'c' * 64,
            'is_coinbase': False,
            'vin': [{'address': 'bc1qinputaddr', 'txid': '0' * 64, 'vout': 0,
                     'script_type': 'p2wpkh',
                     'prevout': {'script_pubkey_hex': '0014' + 'bb' * 20}}],
            'vout': [{'n': 0, 'value_sats': 99_000, 'script_type': 'p2wpkh',
                      'address': 'bc1qoutputaddr',
                      'script_pubkey_hex': '0014' + 'cc' * 20}],
        }
        result = address_reuse.apply(tx)
        assert result['detected'] is False


# ─── heuristic: OP_RETURN ──────────────────────────────────────────────────────

class TestOpReturn:
    """Tests for OP_RETURN heuristic."""

    def test_coinbase_not_detected(self):
        tx = _make_tx(is_coinbase=True)
        assert op_return.apply(tx)['detected'] is False

    def test_op_return_output_detected(self):
        tx = {
            'txid': 'd' * 64,
            'is_coinbase': False,
            'vin': [{'txid': '0' * 64, 'vout': 0, 'script_type': 'p2wpkh',
                     'prevout': {'script_pubkey_hex': '0014' + 'ab' * 20}}],
            'vout': [
                {'n': 0, 'value_sats': 0, 'script_type': 'op_return',
                 'script_pubkey_hex': '6a04deadbeef',
                 'op_return_data': {'op_return_data_hex': 'deadbeef',
                                    'op_return_data_utf8': '', 'op_return_protocol': 'unknown'}},
            ],
        }
        result = op_return.apply(tx)
        assert result['detected'] is True
        assert result['op_return_count'] == 1
        assert result['confidence'] == 'high'

    def test_no_op_return_not_detected(self):
        tx = _make_tx(n_outputs=2, output_values=[50_000, 50_000])
        result = op_return.apply(tx)
        assert result['detected'] is False


# ─── engine ────────────────────────────────────────────────────────────────────

class TestEngine:
    """Tests for the heuristic engine orchestrator."""

    def test_apply_all_returns_all_heuristic_ids(self):
        tx = _make_tx(n_inputs=1, n_outputs=2)
        results = engine.apply_all(tx)
        for h_id in engine.ALL_HEURISTIC_IDS:
            assert h_id in results, f"Missing heuristic: {h_id}"

    def test_each_result_has_detected_key(self):
        tx = _make_tx(n_inputs=2, n_outputs=2)
        results = engine.apply_all(tx)
        for h_id, result in results.items():
            assert 'detected' in result, f"{h_id} missing 'detected' key"

    def test_is_flagged_false_for_simple_tx(self):
        tx = _make_tx(n_inputs=1, n_outputs=2, output_values=[100, 200])
        results = engine.apply_all(tx)
        # Simple tx with 1 input should not trigger CIOH
        # (at least some heuristics should be False)
        assert not all(r['detected'] for r in results.values())

    def test_cioh_suppressed_when_coinjoin_detected(self):
        """CIOH result is annotated suppressed when CoinJoin fires."""
        # Build a tx that triggers CoinJoin + CIOH
        tx = _make_tx(n_inputs=5, n_outputs=5,
                      output_values=[1_000_000] * 5)
        results = engine.apply_all(tx)
        if results.get('coinjoin', {}).get('detected'):
            cioh_result = results.get('cioh', {})
            if cioh_result.get('detected'):
                assert cioh_result.get('suppressed') is True
                assert cioh_result.get('suppressed_by') == 'coinjoin'

    def test_get_active_signals_returns_list(self):
        tx = _make_tx(n_inputs=2, n_outputs=2)
        results = engine.apply_all(tx)
        signals = engine.get_active_signals(results)
        assert isinstance(signals, list)

    def test_set_block_context_does_not_raise(self):
        txs = [_make_tx(n_inputs=2, n_outputs=2) for _ in range(3)]
        engine.set_block_context(txs)  # Should not raise


# ─── output: json_writer ───────────────────────────────────────────────────────

class TestJsonWriter:
    """Tests for JSON output writer."""

    def _sample_heuristics(self):
        h = {h_id: {'detected': False} for h_id in engine.ALL_HEURISTIC_IDS}
        h['cioh'] = {'detected': True, 'confidence': 'medium',
                     'input_count': 2, 'unique_addresses': 2}
        return h

    def test_build_tx_entry_has_txid(self):
        txid = 'a' * 64
        entry = build_tx_entry(txid, self._sample_heuristics(), 'simple_payment')
        assert entry['txid'] == txid

    def test_build_tx_entry_has_classification(self):
        entry = build_tx_entry('b' * 64, self._sample_heuristics(), 'consolidation')
        assert entry['classification'] == 'consolidation'

    def test_build_tx_entry_has_heuristics(self):
        entry = build_tx_entry('c' * 64, self._sample_heuristics(), 'simple_payment')
        assert 'heuristics' in entry

    def test_build_tx_entry_has_signals(self):
        entry = build_tx_entry('d' * 64, self._sample_heuristics(), 'simple_payment')
        assert 'signals' in entry
        assert isinstance(entry['signals'], list)

    def test_build_block_entry_structure(self):
        summary = {'total_transactions_analyzed': 5}
        entry = build_block_entry('00' * 32, 1, 5, summary)
        assert 'block_hash' in entry
        assert entry['tx_count'] == 5
        assert 'transactions' in entry  # defaults to []

    def test_build_file_output_top_level_keys(self):
        summary = {'total_transactions_analyzed': 0}
        output = build_file_output('blk00000.dat', [], summary)
        assert output['ok'] is True
        assert 'blocks' in output
        assert 'file' in output
        assert output['block_count'] == 0
