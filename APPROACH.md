# Approach

This document describes the chain analysis engine ("Sherlock") built to analyze Bitcoin block files. The engine parses raw `.dat` block and undo files, applies 9 privacy/behavioral heuristics to every transaction, classifies transaction types, and produces structured JSON + Markdown reports.

## Architecture

```
blk*.dat + rev*.dat + xor.dat
        │
        ▼
  ┌─────────────────┐
  │   Block Parser   │   XOR decode → header + tx parsing + undo prevout matching
  └────────┬────────┘
           ▼
  ┌─────────────────┐
  │ Heuristic Engine │   9 heuristics applied to each transaction
  └────────┬────────┘
           ▼
  ┌─────────────────┐
  │   Classifier     │   Priority-based tx type classification
  └────────┬────────┘
           ▼
  ┌─────────────────┐
  │  Stats + Output  │   Per-block + file-level aggregation → JSON + Markdown
  └─────────────────┘
```

**Key design decisions:**
- Pure Python 3 with zero external dependencies (no pip install needed)
- Lean parsing mode for blocks beyond the first (skips expensive script disassembly and address encoding to achieve sub-60s runtimes on 84-block files)
- Streaming block parser (reads one block at a time instead of loading full blk files into memory)
- Undo data matching by non-coinbase tx count with SHA256d checksum disambiguation for duplicates
- Deterministic output (no timestamps, no random ordering)

---

## Heuristics Implemented

### 1. Common Input Ownership Heuristic (CIOH)

**What it detects:**
Identifies transactions where multiple inputs are likely controlled by the same entity. In Bitcoin, spending from multiple UTXOs in a single transaction requires the signing keys for all inputs, implying common ownership.

**How it is detected/computed:**
A transaction is flagged if it has more than one non-coinbase input (`len(vin) > 1`). Coinbase transactions are excluded since they have a single synthetic input.

**Confidence model:**
High confidence for standard transactions. The heuristic is the foundational assumption behind most clustering algorithms (Meiklejohn et al., 2013).

**Limitations:**
- **CoinJoin transactions** deliberately combine inputs from different users, producing false positives. The coinjoin heuristic runs separately to identify these.
- **PayJoin** (P2EP) transactions include an input from the payee mixed with the payer's inputs, violating the common-ownership assumption.
- Lightning channel opens that involve multiple funding inputs are correctly flagged but may not represent a privacy concern.

---

### 2. Change Detection

**What it detects:**
Identifies which output in a transaction is the change returned to the sender. Knowing the change output reveals the true payment amount and links the change to the sender's wallet.

**How it is detected/computed:**
Three independent methods are applied in priority order:

1. **Script type match**: If only one output matches the script type of the dominant input type, it is likely change (wallets typically send change to the same address type).
2. **Round number elimination**: If exactly one output has a non-round value (not divisible by 10,000 sats), the other is likely the payment and the non-round one is change.
3. **Value analysis**: The output closest to the total input value (i.e., the larger output) is identified as potential change, since payments are typically smaller than the remaining balance.

Requires exactly 2 spendable (non-OP_RETURN) outputs.

**Confidence model:**
- Script type match: `high` — strong behavioral signal
- Round number: `medium` — common but not universal
- Value analysis: `low` — weak heuristic, many exceptions

**Limitations:**
- Fails on transactions with more than 2 spendable outputs (batch payments)
- Wallets that intentionally match payment and change script types defeat method 1
- Some wallets use a different address type for change (cross-type change)

---

### 3. Address Reuse Detection

**What it detects:**
Identifies when the same address (or scriptPubKey) appears in both inputs and outputs of a transaction, or when the same address funds multiple inputs. Also detects cross-transaction address reuse within the same block. Address reuse degrades privacy by linking UTXOs across transactions.

**How it is detected/computed:**
Collects all input addresses/scriptPubKeys and output addresses/scriptPubKeys. A block-level address index is built before processing transactions to enable cross-transaction detection. Flags if:
- Any address appears in both input set and output set (input-output overlap)
- Any address appears more than once in the input set (duplicate input addresses)
- Any address in this transaction also appears in a different transaction within the same block (cross-transaction reuse)

Uses `script_pubkey_hex` as a fast proxy when full addresses are not computed (lean mode).

**Confidence model:**
High — address reuse is a definitive signal that links UTXOs to the same entity.

**Limitations:**
- Cross-transaction detection is limited to the same block (cannot track reuse across different blocks without a full UTXO index)
- Script-level matching may have rare collisions for non-standard scripts

---

### 4. CoinJoin Detection

**What it detects:**
CoinJoin is a privacy technique where multiple users combine their transactions into one, creating multiple equal-value outputs to obscure the link between inputs and outputs.

**How it is detected/computed:**
Checks for:
- At least `COINJOIN_MIN_INPUTS` inputs (default 2)
- At least `COINJOIN_MIN_EQUAL_OUTPUTS` outputs with identical values (default 2)
- For 2-party CoinJoins (exactly 2 equal outputs), stricter filters apply: equal outputs must represent ≥30% of total value AND ≥40% of output count to reduce false positives

Equal values are counted using exact satoshi comparison.

**Confidence model:**
- High: ≥5 equal outputs with ≥5 inputs, or ≥3 equal outputs forming majority of outputs
- Medium: ≥3 equal outputs in standard configurations
- Low: 2-party CoinJoin (stronger false-positive filters applied)

**Limitations:**
- Does not detect unequal-output CoinJoin (e.g., Knapsack mixing)
- Large batch payments with coincidentally equal amounts may false-positive
- 2-party detection requires strong value/ratio signals to avoid false positives

---

### 5. Consolidation Detection

**What it detects:**
Consolidation transactions sweep many small UTXOs into fewer larger ones, typically during low-fee periods. This is a common wallet management operation.

**How it is detected/computed:**
Flagged when:
- At least `CONSOLIDATION_MIN_INPUTS` inputs (default 3)
- At most 2 spendable (non-OP_RETURN) outputs
- Input count significantly exceeds output count

**Confidence model:**
Medium-high. The input/output ratio strongly suggests consolidation, but exchanges performing withdrawals can have similar patterns.

**Limitations:**
- Simple payments with 3 inputs and 1 output technically match the pattern
- Cannot distinguish between consolidation and a payment that happens to spend multiple UTXOs

---

### 6. Self-Transfer Detection

**What it detects:**
Transactions where a user sends funds entirely to themselves (e.g., moving between own wallets, UTXO management without external payment).

**How it is detected/computed:**
Flagged when all conditions are met:
- All outputs match the dominant input script type
- No outputs have round-number values (suggesting no payment)
- At most 2 outputs (change + destination, both to self)

**Confidence model:**
Medium — strong signal when combined with no round numbers, but can't distinguish from payments to a recipient using the same address type.

**Limitations:**
- If sender and recipient both use p2wpkh (most common type), legitimate payments are misclassified
- Does not use cross-transaction address clustering

---

### 7. Peeling Chain Detection

**What it detects:**
Peeling chains are a pattern where a transaction has exactly 2 outputs with significant value disparity (default threshold ≥5:1). The large output "peels off" a small payment while most funds remain. Within-block spend chain tracking is used to identify connected peeling sequences.

**How it is detected/computed:**
A block-level spend graph is built to track which transactions spend outputs of other transactions in the same block. Then for each transaction, checks:
- At most `PEELING_MAX_INPUTS` inputs (default 3)
- Exactly 2 spendable outputs
- Max output value / min output value ≥ `PEELING_MIN_RATIO` (default 5)
- Optionally: chain evidence (this tx's output is spent by another tx in the same block, or this tx spends from another peeling-like tx)

**Confidence model:**
- High: ratio ≥50, or ratio ≥10 with chain evidence
- Medium: ratio ≥10 without chain evidence, or ratio 5-10 with chain evidence
- Low: ratio 5-10 without chain evidence

**Limitations:**
- Exchange withdrawal batches can create similar patterns
- Ratios between 5:1 and 10:1 are flagged with low confidence to balance recall vs precision

---

### 8. OP_RETURN Data Detection

**What it detects:**
Identifies transactions that embed arbitrary data in the blockchain using OP_RETURN outputs. Classifies the embedded protocol when possible.

**How it is detected/computed:**
Scans all outputs for `script_type == "op_return"`. When detected, attempts to classify protocol markers using extracted payload and script hex:
- **Omni Layer**: data starts with `6f6d6e69` ("omni")
- **OpenTimestamps**: data starts with `0109f91102`
- **Counterparty**: data starts with `434e545250525459` ("CNTRPRTY")
- **Stacks**: data starts with `5354` (ASCII `ST` marker)
- **Runes**: script starts with `6a5d` (OP_RETURN + OP_13 opcode pair, validated at the opcode level rather than data prefix)
- **Text**: valid UTF-8 content

**Confidence model:**
High for protocol detection (magic byte and opcode matching). The presence of OP_RETURN itself is definitive.

**Limitations:**
- Unknown protocols are classified as "unknown_data"
- Does not validate the embedded data's semantic correctness

---

### 9. Round Number Payment Detection

**What it detects:**
Identifies outputs with round BTC values (e.g., 0.1 BTC, 0.01 BTC), which are characteristic of human-initiated payments rather than change outputs.

**How it is detected/computed:**
Tests each output value against round denominations: 100,000,000 sats (1 BTC), 10,000,000 (0.1 BTC), 1,000,000, 100,000, and 10,000 sats. An output is "round" if divisible by any of these thresholds.

**Confidence model:**
Medium — round amounts are strongly correlated with payments but not proof.

**Limitations:**
- Some dust outputs (e.g., 546 sats) are technically round but not meaningful
- Exchanges may use round amounts for internal transfers

---

## Transaction Classification

Transactions are classified using a priority-based decision tree:

| Priority | Classification    | Criteria |
|----------|-------------------|----------|
| 0        | `coinbase`        | Coinbase transaction (miner reward) |
| 1        | `coinjoin`        | CoinJoin heuristic detected |
| 2        | `consolidation`   | Consolidation heuristic detected |
| 3        | `self_transfer`   | Self-transfer heuristic detected |
| 4        | `batch_payment`   | ≥3 spendable outputs (batch withdrawal) |
| 5        | `simple_payment`  | ≤2 spendable outputs with any input count |
| 6        | `unknown`         | All other patterns |

## Trade-offs and Design Decisions

- **Lean mode**: Blocks beyond the first skip `disassemble_script()` and bech32 address encoding, reducing runtime by ~75%. Heuristics use `script_pubkey_hex` comparison instead of addresses for consistency.
- **Undo matching**: Uses tx-count keyed lookup with checksum verification for ambiguous matches, handling files where multiple blocks have the same non-coinbase count.
- **Zero dependencies**: All parsing, encoding (Base58, Bech32/Bech32m), and hashing (SHA-256, RIPEMD-160) implemented in pure Python for maximum portability.
- **CIOH anti-heuristic suppression**: When CoinJoin is detected, CIOH is annotated as `suppressed=True` rather than removed — preserving the raw detection while marking it as a known false positive for downstream consumers.
- **Signals array**: Each transaction includes a `signals` array listing all active heuristic detections with confidence and suppression state, providing richer information than the single classification label alone.
- **Privacy score**: A synthetic 0-100 metric per block that penalizes address reuse, rewards CoinJoin usage, and accounts for round number payments and self-transfers.
- **Fee rate histogram**: Bucket-based fee distribution (`<2`, `2-10`, `10-50`, `50-200`, `>200` sat/vB) reveals distribution shape beyond min/max/median/mean.
- **Configurable thresholds**: Heuristic thresholds are tunable via env vars (`SHERLOCK_COINJOIN_MIN_INPUTS`, `SHERLOCK_COINJOIN_MIN_EQUAL_OUTPUTS`, `SHERLOCK_CONSOLIDATION_MIN_INPUTS`, `SHERLOCK_PEELING_MIN_RATIO`, `SHERLOCK_PEELING_MAX_INPUTS`).

### Lean Mode Limitations

In lean parsing mode (blocks beyond the first), the following limitations apply:

- **Addresses not computed**: `cioh.unique_addresses` falls back to counting unique `script_pubkey_hex` values from prevouts. This is functionally equivalent for most cases but P2PK inputs with no prevout produce empty identifiers.
- **Address reuse**: Uses `script_pubkey_hex` as proxy. Accuracy is equivalent for standard script types but may miss reuse across address encoding formats.
- **Self-transfer**: Cannot use address overlap as a confidence booster since addresses aren't decoded. Detection relies entirely on script type match and round number absence.
- **Script disassembly**: `script_asm` fields are not populated. OP_RETURN protocol detection works on raw hex, so it's unaffected.

## References

- Meiklejohn et al., "A Fistful of Bitcoins", 2013 — CIOH foundation
- BIP173 — Bech32 encoding
- BIP141 — Segregated Witness
- BIP34 — Block height in coinbase
- Maxwell, "CoinJoin: Bitcoin privacy for the real world", 2013
- Nick, "Data-Driven De-Anonymization in Bitcoin", 2015
- Bitcoin Wiki — Address reuse: https://en.bitcoin.it/wiki/Address_reuse
- Bitcoin Wiki — OP_RETURN: https://en.bitcoin.it/wiki/OP_RETURN
- Runes protocol specification (Casey Rodarmor, 2024)
