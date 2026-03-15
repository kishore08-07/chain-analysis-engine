export const fmtNum = n => n == null ? '—' : Number(n).toLocaleString();

export const fmtSats = n => {
  if (n == null) return '—';
  if (n >= 1e8) return (n / 1e8).toFixed(4) + ' BTC';
  if (n >= 1e5) return (n / 1e5).toFixed(1) + 'k sats';
  return fmtNum(n) + ' sats';
};

export const fmtPct = (n, total) => {
  if (!total || total === 0) return '0%';
  return (n / total * 100).toFixed(1) + '%';
};

export const truncTxid = (txid) => {
  if (!txid || txid.length < 16) return txid || '—';
  return txid.substring(0, 10) + '…' + txid.substring(56);
};
