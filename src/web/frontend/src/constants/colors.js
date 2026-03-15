/* Classification color map */
export const CLS_COLORS = {
  simple_payment: { bg: 'var(--accent-bg)', fg: 'var(--accent)', hex: '#58a6ff', cls: 'badge-blue' },
  consolidation:  { bg: 'var(--orange-bg)', fg: 'var(--orange)', hex: '#d29922', cls: 'badge-orange' },
  coinjoin:       { bg: 'var(--purple-bg)', fg: 'var(--purple)', hex: '#bc8cff', cls: 'badge-purple' },
  self_transfer:  { bg: 'var(--pink-bg)',   fg: 'var(--pink)',   hex: '#f778ba', cls: 'badge-pink' },
  batch_payment:  { bg: 'var(--green-bg)',  fg: 'var(--green)',  hex: '#3fb950', cls: 'badge-green' },
  coinbase:       { bg: 'var(--yellow-bg)', fg: 'var(--yellow)', hex: '#e3b341', cls: 'badge-yellow' },
  unknown:        { bg: 'var(--red-bg)',    fg: 'var(--red)',    hex: '#f85149', cls: 'badge-red' },
};

/* Script type colors */
export const SCRIPT_COLORS = {
  p2wpkh: '#58a6ff', p2tr: '#bc8cff', p2pkh: '#d29922',
  p2sh: '#f778ba', p2wsh: '#3fb950', op_return: '#f85149',
  unknown: '#8b949e', multisig: '#da3633', p2pk: '#e3b341',
};

/* Heuristic bar chart colors */
export const HEUR_COLORS = [
  '#58a6ff','#3fb950','#d29922','#bc8cff','#f778ba',
  '#f85149','#39d2c0','#e3b341','#da3633',
];

/* Heuristic human-readable names */
export const HEUR_NAMES = {
  cioh: 'Common Input Ownership',
  change_detection: 'Change Detection',
  address_reuse: 'Address Reuse',
  coinjoin: 'CoinJoin Detection',
  consolidation: 'Consolidation',
  self_transfer: 'Self-Transfer',
  peeling_chain: 'Peeling Chain',
  op_return: 'OP_RETURN Analysis',
  round_number_payment: 'Round Number Payment',
};
