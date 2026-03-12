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
- At least 3 inputs (`len(vin) >= 3`)
- At least 3 outputs with identical values (equal-output CoinJoin pattern)

Equal values are counted using exact satoshi comparison.

**Confidence model:**
High for classic CoinJoin (Wasabi, JoinMarket). Lower confidence for PayJoin or equal-output consolidations.

**Limitations:**
- Does not detect unequal-output CoinJoin (e.g., Knapsack mixing)
- Large batch payments with coincidentally equal amounts may false-positive
- Threshold of 3 may miss smaller 2-party CoinJoins

---

### 5. Consolidation Detection

**What it detects:**
Consolidation transactions sweep many small UTXOs into fewer larger ones, typically during low-fee periods. This is a common wallet management operation.

**How it is detected/computed:**
Flagged when:
- At least 3 inputs
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
Peeling chains are a pattern where a transaction has exactly 2 outputs with a very large value disparity (≥10:1 ratio). The large output "peels off" a small payment while most funds remain. Within-block spend chain tracking is used to identify connected peeling sequences.

**How it is detected/computed:**
A block-level spend graph is built to track which transactions spend outputs of other transactions in the same block. Then for each transaction, checks:
- At most 3 inputs (peeling chains use few inputs)
- Exactly 2 spendable outputs
- Max output value / min output value ≥ 10
- Optionally: chain evidence (this tx's output is spent by another tx in the same block, or this tx spends from another peeling-like tx)

**Confidence model:**
Medium — the ratio threshold is heuristic and may miss peeling chains with closer values.

**Limitations:**
- Exchange withdrawal batches can create similar patterns
- A 10:1 ratio is arbitrary; real peeling chains may have smaller ratios

---

### 8. OP_RETURN Data Detection

**What it detects:**
Identifies transactions that embed arbitrary data in the blockchain using OP_RETURN outputs. Classifies the embedded protocol when possible.

**How it is detected/computed:**
Scans all outputs for `script_type == "op_return"`. When detected, attempts to classify the protocol by examining the data payload:
- **Omni Layer**: starts with `6f6d6e69` ("omni")
- **OpenTimestamps**: starts with `f0105a44` (OTS magic)
- **Counterparty**: starts with `434e545250525459` ("CNTRPRTY")
- **Stacks**: starts with `5834` or `5832` (STX markers)
- **Runes**: starts with `5d` (OP_13 magic byte) or `d8` (Runes marker)
- **Text**: valid UTF-8 content

**Confidence model:**
High for protocol detection (magic byte matching). The presence of OP_RETURN itself is definitive.

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
| 1        | `coinjoin`        | CoinJoin heuristic detected |
| 2        | `consolidation`   | Consolidation heuristic detected |
| 3        | `self_transfer`   | Self-transfer heuristic detected |
| 4        | `batch_payment`   | ≥5 outputs (batch withdrawal) |
| 5        | `simple_payment`  | ≤3 inputs, ≤3 outputs |
| 6        | `unknown`         | All other patterns; coinbase txs |

## Trade-offs and Design Decisions

- **Lean mode**: Blocks beyond the first skip `disassemble_script()` and bech32 address encoding, reducing runtime by ~75%. Heuristics use `script_pubkey_hex` comparison instead of addresses for consistency.
- **Undo matching**: Uses tx-count keyed lookup with checksum verification for ambiguous matches, handling files where multiple blocks have the same non-coinbase count.
- **Zero dependencies**: All parsing, encoding (Base58, Bech32/Bech32m), and hashing (SHA-256, RIPEMD-160) implemented in pure Python for maximum portability.

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
