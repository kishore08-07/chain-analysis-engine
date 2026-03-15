/**
 * Tooltip texts — written in plain language for non-technical users.
 * Think of these as a friendly narrator explaining what each metric really means.
 */

export const TT = {
  /* ── File / Overview ── */
  blocks:
    'A block is like one page in Bitcoin\'s permanent ledger. Each page is sealed and stamped forever — it can never be changed. This tells you how many pages are in this file.',
  transactions:
    'Every time someone sends Bitcoin, it creates a transaction — like writing a cheque. This is the total number of cheques recorded across all the blocks in this file.',
  flagged:
    'Our analysis spotted something worth a second look in these transactions — unusual patterns, privacy techniques, or suspicious clustering. Not all flags mean wrongdoing, but they\'re worth investigating.',
  heuristics:
    'A heuristic is an educated guess based on observable patterns — like how a detective "reads" a scene. We run 9 different detection rules on every transaction.',
  medianFee:
    'The fee a sender pays to have their transaction prioritised by miners. The median is the "middle" value — half of transactions paid more, half paid less. Measured in satoshis per virtual byte (a size unit).',
  feeRange:
    'The cheapest and most expensive transaction fees observed in this block. A wide range often means some senders were in a hurry (paid more), while others could afford to wait.',
  file:
    'This is the Bitcoin Core block file being analysed. Bitcoin Core stores its blockchain in numbered files called blk*.dat.',

  /* ── Classifications ── */
  simple_payment:
    'The classic "A pays B" — one or a few inputs, one payment output, possibly one change output back to the sender. The most common and benign transaction type.',
  consolidation:
    'A wallet sweeping together many small coins into one larger coin — like emptying a piggy bank into a wallet. Often done to reduce future fees.',
  coinjoin:
    'A privacy mixer. Multiple people pool their coins into one transaction and get equal amounts back, making it very hard to trace who paid whom. Think of it as a shuffled card deck.',
  self_transfer:
    'The sender is paying themselves — reorganising their own funds, perhaps moving between wallets. No money actually leaves the sender\'s control.',
  batch_payment:
    'One sender pays many receivers in a single transaction — like a company doing payroll. Efficient, but all outputs can be linked to the same source.',
  coinbase:
    'The very first transaction in every block. It\'s the miner\'s reward — new Bitcoin created from thin air as payment for sealing the block.',
  unknown:
    'We couldn\'t confidently classify this transaction into any of our known patterns. It might be unusual, use an exotic script type, or simply be a rare edge case.',

  /* ── Heuristics ── */
  cioh:
    'Common Input Ownership Heuristic. When multiple coins are spent together, they\'re probably owned by the same person. Foundational to chain analysis since 2013 — like recognising that items in one shopping basket belong to one shopper.',
  change_detection:
    'Every Bitcoin transaction often sends "change" back to the sender, like getting coins back after paying with a note. This heuristic tries to spot which output is the change — identifying the sender\'s own address.',
  address_reuse:
    'Reusing the same Bitcoin address is bad for privacy — it links your past and future payments. Like always signing your letters with the same handwriting, making it easy to build a profile.',
  coinjoin_h:
    'Looks for the equal-output pattern that characterises CoinJoin mixing: multiple inputs, many identical-value outputs. The more equal outputs, the stronger the signal.',
  consolidation_h:
    'Many inputs flowing into very few outputs. Classic wallet housekeeping — like depositing a jar of coins into a bank account.',
  self_transfer_h:
    'All outputs appear to go to addresses that match the sender\'s input script types, suggesting zero external payment is happening.',
  peeling_chain:
    'A transaction pattern where one output is always spent in the very next transaction, like peeling layers off an onion. Often seen in payment forwarding or tumbler chains.',
  op_return:
    'OP_RETURN outputs embed arbitrary data in the blockchain — like carving text into stone. Used for Runes inscriptions, NFTs, timestamping, and more. The data is provably permanent.',
  round_number_payment:
    'Sending exactly 0.001 BTC or 100,000 sats? That\'s suspicious precision — real prices are rarely round. Round amounts strongly suggest a deliberate payment rather than automatic change.',

  /* ── Script types ── */
  p2wpkh:
    'Pay-to-Witness-Public-Key-Hash. The modern standard for single-key wallets. Faster, cheaper, and more private than the legacy format. Like an upgraded padlock.',
  p2tr:
    'Pay-to-Taproot. Bitcoin\'s newest and most private format. It makes all transactions — even complex smart contracts — look identical from the outside.',
  p2pkh:
    'Pay-to-Public-Key-Hash. The original Bitcoin address format (starts with "1"). Works but is the most expensive and least private. Still widely used.',
  p2sh:
    'Pay-to-Script-Hash. A flexible format that allows multisig wallets and other conditions (starts with "3"). Like a lock that requires multiple keys.',
  p2wsh:
    'Pay-to-Witness-Script-Hash. The SegWit version of P2SH — same flexibility but updated and cheaper to verify.',
  multisig:
    'Requires M-of-N signatures to unlock funds — like a safe that needs two keyholders. Used by exchanges and high-security wallets.',
  op_return_st:
    'Not a real payment output — just a data carrier. Cannot be spent. Used to permanently record information on the blockchain.',
  unknown_st:
    'A script type our parser doesn\'t recognise — possibly a new format, a custom covenant, or malformed data.',

  /* ── Fee chart ── */
  feeMin: 'The lowest fee rate paid across all transactions in this block. These senders were patient — willing to wait longer for confirmation.',
  feeMedian: 'Half the transactions paid less than this, half paid more. The median is more reliable than the average because it ignores extreme outliers.',
  feeMean: 'The mathematical average fee rate. Skewed upward whenever a few senders pay very high fees to jump the queue instantly.',
  feeMax: 'The highest fee rate paid — likely someone who needed to confirm immediately and paid whatever it took.',

  /* ── Privacy score ── */
  privacyScore:
    'A synthetic score (0–100) measuring how privacy-friendly this block\'s transactions appear. Penalises address reuse and heavy clustering; rewards CoinJoin usage and diverse script types.',

  /* ── Table columns ── */
  txTxid: 'Transaction ID — the unique fingerprint of this transaction. Every transaction gets its own hash, derived from its content.',
  txClassification: 'The pattern our engine identified for this transaction — like labelling a letter "invoice" or "receipt".',
  txInOut: 'Inputs → Outputs. How many coins were consumed and how many were created. In Bitcoin, you always spend whole coins and get change back.',
  txFeeRate: 'How much the sender paid per virtual byte of data. Higher fee = faster confirmation. Expressed in satoshis per virtual byte (sat/vB).',
  txHeuristics: 'Which detection rules fired for this transaction. Each red badge is a heuristic pattern that was detected.',
  txSuppressed: 'This heuristic fired, but its result is overridden by a stronger signal. CoinJoin, for example, invalidates the common-input-ownership assumption.',

  /* ── Block explorer ── */
  blockHeight: 'The sequential number of this block in the entire Bitcoin blockchain — like a page number. Block 0 is the very first block (Genesis) mined in 2009.',
  blockHash: "The unique fingerprint of this block's data. Changing even one character inside the block would produce a completely different hash — making tampering detectable.",
  blockTime: 'The approximate wall-clock time when this block was mined. Miners set this themselves, so it\'s accurate to within a few hours.',
};

export default TT;
