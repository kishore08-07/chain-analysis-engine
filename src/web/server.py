"""
Sherlock Web Visualizer — Python HTTP Server

Serves:
  - GET /api/health → { "ok": true }
  - GET /api/files → list of available analysis files
  - GET /api/analysis/<blk_stem> → full JSON analysis for a block file
  - GET / → React SPA (single-page app)
  - GET /static/* → static assets

Uses only Python stdlib (http.server, json, os).
"""

import http.server
import json
import os
import sys
import signal
import socketserver

# Project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(PROJECT_ROOT, 'out')
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')


MIME_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript',
    '.css': 'text/css',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
    '.ttf': 'font/ttf',
    '.map': 'application/json',
}


class SherlockHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for Sherlock web visualizer."""

    def log_message(self, format, *args):
        """Suppress default logging to keep stdout clean."""
        pass

    def _send_json(self, data, status=200):
        """Send a JSON response."""
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html, status=200):
        """Send an HTML response."""
        body = html.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, filepath, content_type):
        """Send a file as response."""
        try:
            with open(filepath, 'rb') as f:
                body = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'public, max-age=31536000, immutable')
            self.end_headers()
            self.wfile.write(body)
        except FileNotFoundError:
            self._send_json({'error': 'Not found'}, 404)

    def _serve_static(self, rel_path):
        """Serve a static file from the STATIC_DIR."""
        # Prevent directory traversal
        safe_path = os.path.normpath(rel_path).lstrip('/')
        if '..' in safe_path:
            self._send_json({'error': 'Forbidden'}, 403)
            return
        filepath = os.path.join(STATIC_DIR, safe_path)
        if not os.path.isfile(filepath):
            self._send_json({'error': 'Not found'}, 404)
            return
        ext = os.path.splitext(filepath)[1].lower()
        content_type = MIME_TYPES.get(ext, 'application/octet-stream')
        self._send_file(filepath, content_type)

    def _serve_index_html(self):
        """Serve the SPA index.html from static build, or fallback to embedded."""
        index_path = os.path.join(STATIC_DIR, 'index.html')
        if os.path.isfile(index_path):
            self._send_file(index_path, 'text/html; charset=utf-8')
        else:
            self._send_html(get_spa_html())

    def do_GET(self):
        """Handle GET requests."""
        path = self.path.split('?')[0]  # Strip query params

        if path == '/api/health':
            self._send_json({'ok': True})

        elif path == '/api/files':
            self._handle_files_list()

        elif path.startswith('/api/analysis/'):
            blk_stem = path[len('/api/analysis/'):]
            self._handle_analysis(blk_stem)

        elif path.startswith('/assets/'):
            self._serve_static(path[1:])  # Strip leading /

        elif path == '/' or path == '/index.html':
            self._serve_index_html()

        else:
            # Try serving as static file first, then fallback to SPA
            rel = path.lstrip('/')
            static_file = os.path.join(STATIC_DIR, rel)
            if rel and os.path.isfile(static_file):
                ext = os.path.splitext(static_file)[1].lower()
                content_type = MIME_TYPES.get(ext, 'application/octet-stream')
                self._send_file(static_file, content_type)
            else:
                self._serve_index_html()

    def _handle_files_list(self):
        """Return list of available analysis files."""
        files = []
        if os.path.isdir(OUT_DIR):
            for f in sorted(os.listdir(OUT_DIR)):
                if f.endswith('.json'):
                    stem = f[:-5]  # Remove .json
                    filepath = os.path.join(OUT_DIR, f)
                    try:
                        size = os.path.getsize(filepath)
                        # Read just the top-level summary without full tx data
                        with open(filepath, 'r') as fh:
                            data = json.load(fh)
                        files.append({
                            'stem': stem,
                            'filename': f,
                            'size_bytes': size,
                            'block_count': data.get('block_count', 0),
                            'total_transactions': data.get('analysis_summary', {}).get('total_transactions_analyzed', 0),
                            'flagged_transactions': data.get('analysis_summary', {}).get('flagged_transactions', 0),
                        })
                    except Exception:
                        files.append({'stem': stem, 'filename': f, 'error': True})
        self._send_json({'ok': True, 'files': files})

    def _handle_analysis(self, blk_stem):
        """Return full analysis JSON for a block file."""
        json_path = os.path.join(OUT_DIR, f'{blk_stem}.json')
        if not os.path.isfile(json_path):
            self._send_json({'ok': False, 'error': f'File not found: {blk_stem}.json'}, 404)
            return
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
            self._send_json(data)
        except Exception as e:
            self._send_json({'ok': False, 'error': str(e)}, 500)


def get_spa_html():
    """Return the single-page React application HTML."""
    return SPA_HTML


# The React SPA is embedded as a string to avoid any build step
SPA_HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sherlock — Bitcoin Chain Analysis</title>
  <script src="https://unpkg.com/react@18/umd/react.production.min.js" crossorigin></script>
  <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js" crossorigin></script>
  <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
  <style>
    :root {
      --bg: #0a0e14; --surface: #131921; --surface2: #1a2233;
      --surface3: #222d3d; --border: #2a3545; --border-light: #3a4a5e;
      --text: #e6edf3; --text-muted: #8b949e; --text-dim: #6e7681;
      --accent: #58a6ff; --accent-bg: #1f6feb22;
      --green: #3fb950; --green-bg: #23883022;
      --red: #f85149; --red-bg: #f8514922;
      --orange: #d29922; --orange-bg: #d2992222;
      --purple: #bc8cff; --purple-bg: #bc8cff22;
      --pink: #f778ba; --pink-bg: #f778ba22;
      --yellow: #e3b341; --yellow-bg: #e3b34122;
      --cyan: #39d2c0; --cyan-bg: #39d2c022;
      --radius: 10px; --radius-sm: 6px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
      background: var(--bg); color: var(--text); line-height: 1.6;
      -webkit-font-smoothing: antialiased;
    }
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: var(--bg); }
    ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }

    .container { max-width: 1440px; margin: 0 auto; padding: 0 24px; }

    /* Header */
    .header {
      background: linear-gradient(180deg, #131921 0%, var(--bg) 100%);
      border-bottom: 1px solid var(--border);
      padding: 20px 0; position: sticky; top: 0; z-index: 100;
      backdrop-filter: blur(12px);
    }
    .header-inner {
      display: flex; align-items: center; gap: 16px;
      max-width: 1440px; margin: 0 auto; padding: 0 24px;
    }
    .logo { font-size: 28px; font-weight: 700; }
    .logo span { color: var(--accent); }
    .subtitle { color: var(--text-muted); font-size: 14px; }
    .api-badge {
      margin-left: auto; font-size: 12px; padding: 4px 10px;
      border-radius: 12px; background: var(--green-bg); color: var(--green);
      border: 1px solid #23883044;
    }

    /* Badges */
    .badge {
      display: inline-flex; align-items: center; gap: 4px;
      padding: 3px 10px; border-radius: 12px;
      font-size: 12px; font-weight: 500; white-space: nowrap;
    }
    .badge-blue { background: var(--accent-bg); color: var(--accent); }
    .badge-green { background: var(--green-bg); color: var(--green); }
    .badge-red { background: var(--red-bg); color: var(--red); }
    .badge-orange { background: var(--orange-bg); color: var(--orange); }
    .badge-purple { background: var(--purple-bg); color: var(--purple); }
    .badge-pink { background: var(--pink-bg); color: var(--pink); }
    .badge-yellow { background: var(--yellow-bg); color: var(--yellow); }
    .badge-cyan { background: var(--cyan-bg); color: var(--cyan); }

    /* Cards */
    .card {
      background: var(--surface); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 20px; margin-bottom: 16px;
    }
    .card-header {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 16px;
    }
    .card h2 { font-size: 16px; font-weight: 600; color: var(--text); }
    .card h3 { font-size: 13px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; }

    /* Stat Grid */
    .stat-grid {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
    }
    .stat-box {
      background: var(--surface2); border-radius: var(--radius-sm);
      padding: 14px; text-align: center; border: 1px solid var(--border);
      transition: border-color 0.2s;
    }
    .stat-box:hover { border-color: var(--accent); }
    .stat-box .value { font-size: 26px; font-weight: 700; color: var(--accent); line-height: 1.2; }
    .stat-box .label { font-size: 11px; color: var(--text-muted); margin-top: 4px; text-transform: uppercase; letter-spacing: 0.3px; }

    /* Two-column dashboard */
    .dash-grid {
      display: grid; grid-template-columns: 1fr 1fr;
      gap: 16px; margin-bottom: 16px;
    }
    @media (max-width: 900px) { .dash-grid { grid-template-columns: 1fr; } }

    /* Tables */
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); }
    th { color: var(--text-muted); font-weight: 500; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; position: sticky; top: 0; background: var(--surface); }
    tr.tx-row { cursor: pointer; transition: background 0.15s; }
    tr.tx-row:hover { background: var(--surface2); }
    tr.tx-row.expanded { background: var(--surface2); }

    /* Donut Chart */
    .donut-container {
      display: flex; align-items: center; gap: 24px; padding: 8px 0;
    }
    .donut-legend {
      display: flex; flex-direction: column; gap: 6px; font-size: 12px;
    }
    .donut-legend-item {
      display: flex; align-items: center; gap: 8px; cursor: pointer;
      padding: 3px 6px; border-radius: 4px; transition: background 0.15s;
    }
    .donut-legend-item:hover { background: var(--surface2); }
    .legend-swatch { width: 12px; height: 12px; border-radius: 3px; flex-shrink: 0; }
    .legend-label { color: var(--text-muted); }
    .legend-value { font-weight: 600; color: var(--text); margin-left: auto; padding-left: 12px; }

    /* Horizontal Bars */
    .h-bars { display: flex; flex-direction: column; gap: 8px; }
    .h-bar-row { display: flex; align-items: center; gap: 10px; }
    .h-bar-label { font-size: 11px; color: var(--text-muted); width: 130px; text-align: right; flex-shrink: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .h-bar-track { flex: 1; height: 20px; background: var(--surface2); border-radius: 3px; overflow: hidden; position: relative; }
    .h-bar-fill { height: 100%; border-radius: 3px; transition: width 0.5s ease; min-width: 2px; }
    .h-bar-value { font-size: 11px; color: var(--text-muted); width: 70px; flex-shrink: 0; }

    /* Script type stacked bar */
    .script-bar { display: flex; height: 24px; border-radius: 4px; overflow: hidden; }
    .script-bar div { height: 100%; transition: width 0.4s ease; }
    .script-legend { display: flex; flex-wrap: wrap; gap: 12px; font-size: 12px; margin-top: 10px; }
    .script-legend-item { display: flex; align-items: center; gap: 5px; }
    .script-swatch { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }

    /* File selector */
    .file-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; margin: 24px 0; }
    .file-card {
      background: var(--surface); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 20px; cursor: pointer;
      transition: all 0.2s; position: relative; overflow: hidden;
    }
    .file-card::before {
      content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
      background: linear-gradient(90deg, var(--accent), var(--purple));
      opacity: 0; transition: opacity 0.2s;
    }
    .file-card:hover { border-color: var(--accent); transform: translateY(-2px); box-shadow: 0 4px 16px #00000044; }
    .file-card:hover::before { opacity: 1; }
    .file-card.active { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
    .file-card.active::before { opacity: 1; }
    .file-card h3 { font-size: 18px; margin-bottom: 8px; font-weight: 600; }
    .file-card .meta { font-size: 13px; color: var(--text-muted); line-height: 1.8; }
    .file-card .meta strong { color: var(--text); }

    /* Block tabs */
    .block-tabs { display: flex; gap: 4px; flex-wrap: wrap; overflow-x: auto; padding: 2px; }
    .block-tab {
      padding: 6px 14px; background: var(--surface2); border: 1px solid var(--border);
      border-radius: var(--radius-sm); cursor: pointer; font-size: 12px;
      color: var(--text-muted); white-space: nowrap; transition: all 0.15s;
    }
    .block-tab:hover { border-color: var(--accent); color: var(--text); }
    .block-tab.active { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }

    /* Filter bar */
    .filter-bar { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; align-items: center; }
    .filter-bar input, .filter-bar select {
      background: var(--surface2); border: 1px solid var(--border);
      color: var(--text); padding: 8px 14px; border-radius: var(--radius-sm);
      font-size: 13px; outline: none; transition: border-color 0.2s;
    }
    .filter-bar input:focus, .filter-bar select:focus { border-color: var(--accent); }
    .filter-bar input { width: 280px; }
    .filter-bar input::placeholder { color: var(--text-dim); }
    .btn {
      background: var(--surface2); border: 1px solid var(--border);
      color: var(--text-muted); padding: 8px 16px; border-radius: var(--radius-sm);
      cursor: pointer; font-size: 13px; transition: all 0.15s; font-weight: 500;
    }
    .btn:hover { background: var(--surface3); color: var(--text); border-color: var(--border-light); }
    .btn.active { background: var(--accent); border-color: var(--accent); color: #fff; }

    /* Tx Detail Panel */
    .tx-detail { background: var(--surface2); border-radius: var(--radius-sm); padding: 20px; margin: 4px 0 8px; }
    .tx-detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    @media (max-width: 768px) { .tx-detail-grid { grid-template-columns: 1fr; } }
    .heuristic-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 8px; }
    .heuristic-item {
      display: flex; align-items: center; gap: 8px;
      padding: 8px 10px; border-radius: var(--radius-sm); font-size: 12px;
    }
    .heuristic-item.detected { background: var(--red-bg); border: 1px solid #f8514933; }
    .heuristic-item.not-detected { background: var(--surface); opacity: 0.5; }
    .dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .dot.on { background: var(--red); box-shadow: 0 0 6px var(--red); }
    .dot.off { background: var(--text-dim); }

    /* Tx Flow Visualization */
    .tx-flow { margin-top: 12px; }
    .tx-flow svg text { font-family: inherit; }
    .flow-input-line { stroke: var(--accent); stroke-width: 1.5; opacity: 0.6; }
    .flow-output-line { stroke: var(--green); stroke-width: 1.5; opacity: 0.6; }
    .flow-dot-in { fill: var(--accent); }
    .flow-dot-out { fill: var(--green); }
    .flow-tx-box { fill: var(--surface3); stroke: var(--border-light); rx: 6; }

    /* Pagination */
    .pagination { display: flex; justify-content: center; align-items: center; gap: 12px; margin-top: 16px; }

    /* Loading */
    .loading { text-align: center; padding: 60px; color: var(--text-muted); }
    .loading .spinner {
      width: 32px; height: 32px; border: 3px solid var(--border);
      border-top-color: var(--accent); border-radius: 50%;
      animation: spin 0.8s linear infinite; margin: 0 auto 12px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    /* Tab bar */
    .view-tabs { display: flex; gap: 2px; margin-bottom: 20px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 4px; }
    .view-tab {
      flex: 1; text-align: center; padding: 10px; border-radius: var(--radius-sm);
      cursor: pointer; font-size: 13px; font-weight: 500; color: var(--text-muted);
      transition: all 0.15s;
    }
    .view-tab:hover { color: var(--text); background: var(--surface2); }
    .view-tab.active { color: #fff; background: var(--accent); }

    .empty-state { text-align: center; padding: 60px 20px; color: var(--text-muted); }
    .empty-state .icon { font-size: 48px; margin-bottom: 12px; }
    .empty-state p { max-width: 400px; margin: 0 auto; }

    /* Fee rate visual */
    .fee-visual { display: flex; align-items: center; gap: 8px; margin-top: 12px; padding: 10px; background: var(--surface2); border-radius: var(--radius-sm); }
    .fee-bar-container { flex: 1; position: relative; height: 28px; background: var(--surface3); border-radius: 4px; overflow: visible; }
    .fee-range-bar { position: absolute; height: 100%; background: linear-gradient(90deg, var(--accent), var(--purple)); border-radius: 4px; opacity: 0.3; }
    .fee-median-marker { position: absolute; width: 3px; height: 100%; background: var(--accent); border-radius: 2px; top: 0; }
    .fee-mean-marker { position: absolute; width: 3px; height: 100%; background: var(--purple); border-radius: 2px; top: 0; border: 1px dashed var(--purple); }
    .fee-label { font-size: 10px; color: var(--text-dim); text-align: center; }

    @media (max-width: 768px) {
      .stat-grid { grid-template-columns: repeat(2, 1fr); }
      .filter-bar input { width: 100%; }
    }
  </style>
</head>
<body>
  <div id="root"></div>
  <script type="text/babel">
    const { useState, useEffect, useMemo, useCallback, useRef } = React;

    /* Color maps */
    const CLS_COLORS = {
      simple_payment: { bg: 'var(--accent-bg)', fg: 'var(--accent)', hex: '#58a6ff', cls: 'badge-blue' },
      consolidation:  { bg: 'var(--orange-bg)', fg: 'var(--orange)', hex: '#d29922', cls: 'badge-orange' },
      coinjoin:       { bg: 'var(--purple-bg)', fg: 'var(--purple)', hex: '#bc8cff', cls: 'badge-purple' },
      self_transfer:  { bg: 'var(--pink-bg)',   fg: 'var(--pink)',   hex: '#f778ba', cls: 'badge-pink' },
      batch_payment:  { bg: 'var(--green-bg)',  fg: 'var(--green)',  hex: '#3fb950', cls: 'badge-green' },
      coinbase:       { bg: 'var(--yellow-bg)', fg: 'var(--yellow)', hex: '#e3b341', cls: 'badge-yellow' },
      unknown:        { bg: 'var(--red-bg)',    fg: 'var(--red)',    hex: '#f85149', cls: 'badge-red' },
    };

    const SCRIPT_COLORS = {
      p2wpkh: '#58a6ff', p2tr: '#bc8cff', p2pkh: '#d29922',
      p2sh: '#f778ba', p2wsh: '#3fb950', op_return: '#f85149',
      unknown: '#8b949e', multisig: '#da3633', p2pk: '#e3b341',
    };

    const HEUR_COLORS = [
      '#58a6ff','#3fb950','#d29922','#bc8cff','#f778ba',
      '#f85149','#39d2c0','#e3b341','#da3633',
    ];

    const fmtNum = n => n == null ? '—' : Number(n).toLocaleString();
    const fmtSats = n => {
      if (n == null) return '—';
      if (n >= 1e8) return (n / 1e8).toFixed(4) + ' BTC';
      if (n >= 1e5) return (n / 1e5).toFixed(1) + 'k sats';
      return fmtNum(n) + ' sats';
    };

    /* ===================== APP ===================== */
    function App() {
      const [files, setFiles] = useState([]);
      const [selFile, setSelFile] = useState(null);
      const [data, setData] = useState(null);
      const [loading, setLoading] = useState(true);
      const [view, setView] = useState('dashboard');
      const [selBlock, setSelBlock] = useState(0);

      useEffect(() => {
        fetch('/api/files').then(r => r.json()).then(d => {
          setFiles(d.files || []); setLoading(false);
        }).catch(() => setLoading(false));
      }, []);

      const loadFile = useCallback(stem => {
        setLoading(true); setSelFile(stem); setSelBlock(0); setView('dashboard');
        fetch(`/api/analysis/${stem}`).then(r => r.json()).then(d => {
          setData(d); setLoading(false);
        }).catch(() => setLoading(false));
      }, []);

      return (
        <div>
          <div className="header">
            <div className="header-inner">
              <div className="logo">&#128269; <span>Sherlock</span></div>
              <div className="subtitle">Bitcoin Chain Analysis Engine</div>
              <div className="api-badge">● API Health OK</div>
            </div>
          </div>
          <div className="container" style={{paddingTop: 24, paddingBottom: 60}}>
            {/* File selector */}
            <div className="file-list">
              {files.map(f => (
                <div key={f.stem} className={`file-card ${selFile === f.stem ? 'active' : ''}`}
                  onClick={() => loadFile(f.stem)}>
                  <h3>&#128230; {f.filename}</h3>
                  <div className="meta">
                    <strong>{f.block_count}</strong> blocks &middot;
                    <strong> {fmtNum(f.total_transactions)}</strong> transactions<br/>
                    <span style={{color:'var(--red)'}}>&#9873; {fmtNum(f.flagged_transactions)} flagged</span>
                  </div>
                </div>
              ))}
              {files.length === 0 && !loading && (
                <div className="empty-state" style={{gridColumn:'1/-1'}}>
                  <div className="icon">&#128269;</div>
                  <p>No analysis files found. Run <code>cli.sh</code> first to analyze block data.</p>
                </div>
              )}
            </div>

            {loading && <div className="loading"><div className="spinner"></div>Loading analysis data...</div>}

            {data && !loading && (
              <div>
                {/* View tabs */}
                <div className="view-tabs">
                  <div className={`view-tab ${view==='dashboard'?'active':''}`} onClick={()=>setView('dashboard')}>&#128202; Dashboard</div>
                  <div className={`view-tab ${view==='blocks'?'active':''}`} onClick={()=>setView('blocks')}>&#9638; Blocks</div>
                  <div className={`view-tab ${view==='transactions'?'active':''}`} onClick={()=>setView('transactions')}>&#128176; Transactions</div>
                </div>

                {view === 'dashboard' && <Dashboard data={data} />}
                {view === 'blocks' && <BlockExplorer data={data} selBlock={selBlock} setSelBlock={setSelBlock} />}
                {view === 'transactions' && <TransactionExplorer data={data} selBlock={selBlock} setSelBlock={setSelBlock} />}
              </div>
            )}
          </div>
        </div>
      );
    }

    /* ===================== DASHBOARD ===================== */
    function Dashboard({ data }) {
      const summary = data.analysis_summary || {};
      const feeStats = summary.fee_rate_stats || {};
      const scriptDist = summary.script_type_distribution || {};
      const classDist = summary.classification_distribution || {};
      const hCounts = summary.heuristic_detection_counts || {};
      const totalTxs = summary.total_transactions_analyzed || 0;

      return (
        <div>
          {/* Key stats */}
          <div className="card">
            <h2>&#128202; Analysis Overview — {data.file}</h2>
            <div style={{marginTop:16}} className="stat-grid">
              <StatBox value={data.block_count} label="Blocks" />
              <StatBox value={fmtNum(totalTxs)} label="Transactions" raw />
              <StatBox value={fmtNum(summary.flagged_transactions||0)} label="Flagged" color="var(--red)" raw />
              <StatBox value={(summary.heuristics_applied||[]).length} label="Heuristics" />
              <StatBox value={feeStats.median_sat_vb || 0} label="Median Fee (sat/vB)" />
              <StatBox value={`${feeStats.min_sat_vb||0} — ${feeStats.max_sat_vb||0}`} label="Fee Range" raw />
            </div>
          </div>

          {/* Two-column dashboard */}
          <div className="dash-grid">
            {/* Classification Donut */}
            <div className="card">
              <h3>Transaction Classifications</h3>
              <DonutChart data={classDist} colorMap={CLS_COLORS} total={totalTxs} />
            </div>

            {/* Heuristic Detection Frequencies */}
            <div className="card">
              <h3>Heuristic Detection Frequency</h3>
              <HeuristicBars counts={hCounts} total={totalTxs} heuristics={summary.heuristics_applied||[]} />
            </div>
          </div>

          <div className="dash-grid">
            {/* Script type distribution */}
            <div className="card">
              <h3>Script Type Distribution</h3>
              <ScriptTypeBar dist={scriptDist} />
            </div>

            {/* Fee rate visual */}
            <div className="card">
              <h3>Fee Rate Distribution</h3>
              <FeeRateViz stats={feeStats} />
            </div>
          </div>
        </div>
      );
    }

    /* ===================== DONUT CHART ===================== */
    function DonutChart({ data, colorMap, total }) {
      const entries = Object.entries(data).sort((a,b) => b[1] - a[1]);
      const sum = entries.reduce((a, [,v]) => a + v, 0);
      if (sum === 0) return <div style={{color:'var(--text-muted)',fontSize:13}}>No classification data</div>;

      const size = 180, cx = size/2, cy = size/2, r = 65, thickness = 28;
      const circumference = 2 * Math.PI * r;
      let offset = 0;

      return (
        <div className="donut-container">
          <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
            {/* Background ring */}
            <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--surface2)" strokeWidth={thickness} />
            {entries.map(([label, value]) => {
              const dashLen = (value / sum) * circumference;
              const el = (
                <circle key={label} cx={cx} cy={cy} r={r}
                  fill="none" stroke={(colorMap[label]||{}).hex || '#8b949e'}
                  strokeWidth={thickness}
                  strokeDasharray={`${dashLen} ${circumference - dashLen}`}
                  strokeDashoffset={-offset}
                  transform={`rotate(-90 ${cx} ${cy})`}
                  style={{transition: 'stroke-dasharray 0.5s ease'}}
                />
              );
              offset += dashLen;
              return el;
            })}
            <text x={cx} y={cy-6} textAnchor="middle" fill="var(--text)" fontSize="22" fontWeight="700">{fmtNum(sum)}</text>
            <text x={cx} y={cy+14} textAnchor="middle" fill="var(--text-muted)" fontSize="10">transactions</text>
          </svg>
          <div className="donut-legend">
            {entries.map(([label, value]) => (
              <div key={label} className="donut-legend-item">
                <div className="legend-swatch" style={{background: (colorMap[label]||{}).hex || '#8b949e'}} />
                <span className="legend-label">{label.replace(/_/g,' ')}</span>
                <span className="legend-value">{fmtNum(value)} <span style={{color:'var(--text-dim)',fontWeight:400}}>({(value/sum*100).toFixed(1)}%)</span></span>
              </div>
            ))}
          </div>
        </div>
      );
    }

    /* ===================== HEURISTIC BARS ===================== */
    function HeuristicBars({ counts, total, heuristics }) {
      const ids = heuristics.length > 0 ? heuristics : Object.keys(counts);
      const sorted = ids.map(id => [id, counts[id] || 0]).sort((a,b) => b[1] - a[1]);
      const max = sorted.length > 0 ? Math.max(sorted[0][1], 1) : 1;

      return (
        <div className="h-bars">
          {sorted.map(([id, count], i) => (
            <div key={id} className="h-bar-row">
              <div className="h-bar-label">{id.replace(/_/g,' ')}</div>
              <div className="h-bar-track">
                <div className="h-bar-fill"
                  style={{width: `${(count/max)*100}%`, background: HEUR_COLORS[i % HEUR_COLORS.length]}} />
              </div>
              <div className="h-bar-value">{fmtNum(count)} ({total > 0 ? (count/total*100).toFixed(1) : 0}%)</div>
            </div>
          ))}
        </div>
      );
    }

    /* ===================== SCRIPT TYPE BAR ===================== */
    function ScriptTypeBar({ dist }) {
      const entries = Object.entries(dist).sort((a,b) => b[1] - a[1]);
      const total = entries.reduce((a, [,v]) => a + v, 0);
      if (total === 0) return null;

      return (
        <div>
          <div className="script-bar">
            {entries.map(([type, count]) => (
              <div key={type}
                style={{width: `${(count/total)*100}%`, background: SCRIPT_COLORS[type] || '#8b949e'}}
                title={`${type}: ${fmtNum(count)} (${(count/total*100).toFixed(1)}%)`}
              />
            ))}
          </div>
          <div className="script-legend">
            {entries.map(([type, count]) => (
              <div key={type} className="script-legend-item">
                <span className="script-swatch" style={{background: SCRIPT_COLORS[type] || '#8b949e'}} />
                <span style={{color:'var(--text-muted)'}}>{type}</span>
                <span style={{fontWeight:600}}>{fmtNum(count)}</span>
                <span style={{color:'var(--text-dim)'}}>({(count/total*100).toFixed(1)}%)</span>
              </div>
            ))}
          </div>
        </div>
      );
    }

    /* ===================== FEE RATE VISUALIZATION ===================== */
    function FeeRateViz({ stats }) {
      if (!stats || !stats.max_sat_vb) return <div style={{color:'var(--text-muted)',fontSize:13}}>No fee data</div>;
      const { min_sat_vb, max_sat_vb, median_sat_vb, mean_sat_vb } = stats;
      const range = max_sat_vb - min_sat_vb || 1;
      const medianPct = ((median_sat_vb - min_sat_vb) / range) * 100;
      const meanPct = ((mean_sat_vb - min_sat_vb) / range) * 100;

      return (
        <div>
          <div className="stat-grid" style={{gridTemplateColumns:'repeat(4,1fr)',marginBottom:12}}>
            <div className="stat-box"><div className="value" style={{fontSize:18}}>{min_sat_vb}</div><div className="label">Min</div></div>
            <div className="stat-box"><div className="value" style={{fontSize:18,color:'var(--accent)'}}>{median_sat_vb}</div><div className="label">Median</div></div>
            <div className="stat-box"><div className="value" style={{fontSize:18,color:'var(--purple)'}}>{mean_sat_vb}</div><div className="label">Mean</div></div>
            <div className="stat-box"><div className="value" style={{fontSize:18}}>{max_sat_vb}</div><div className="label">Max</div></div>
          </div>
          <div className="fee-visual">
            <div className="fee-label">{min_sat_vb}<br/>min</div>
            <div className="fee-bar-container">
              <div className="fee-range-bar" style={{left:'0%',width:'100%'}} />
              <div className="fee-median-marker" style={{left:`${medianPct}%`}} title={`Median: ${median_sat_vb}`} />
              <div className="fee-mean-marker" style={{left:`${meanPct}%`}} title={`Mean: ${mean_sat_vb}`} />
            </div>
            <div className="fee-label">{max_sat_vb}<br/>max</div>
          </div>
          <div style={{display:'flex',justifyContent:'center',gap:20,marginTop:8,fontSize:11}}>
            <span style={{color:'var(--accent)'}}>&#9646; Median</span>
            <span style={{color:'var(--purple)'}}>&#9482; Mean</span>
          </div>
        </div>
      );
    }

    /* ===================== STAT BOX ===================== */
    function StatBox({ value, label, color, raw }) {
      return (
        <div className="stat-box">
          <div className="value" style={color ? {color} : {}}>{raw ? value : fmtNum(value)}</div>
          <div className="label">{label}</div>
        </div>
      );
    }

    /* ===================== BLOCK EXPLORER ===================== */
    function BlockExplorer({ data, selBlock, setSelBlock }) {
      const blocks = data.blocks || [];
      const block = blocks[selBlock];

      return (
        <div>
          <div className="card">
            <div className="card-header">
              <h2>&#9638; Block Explorer ({blocks.length} blocks)</h2>
            </div>
            <div className="block-tabs">
              {blocks.map((b, i) => (
                <div key={i} className={`block-tab ${selBlock === i ? 'active' : ''}`}
                  onClick={() => setSelBlock(i)}>
                  #{b.block_height || i}
                </div>
              ))}
            </div>
          </div>

          {block && <BlockDetail block={block} index={selBlock} />}
        </div>
      );
    }

    function BlockDetail({ block, index }) {
      const summary = block.analysis_summary || {};
      const feeStats = summary.fee_rate_stats || {};
      const scriptDist = summary.script_type_distribution || {};
      const classDist = summary.classification_distribution || {};
      const hCounts = summary.heuristic_detection_counts || {};
      const txs = block.transactions || [];
      const hasTxs = txs.length > 0;
      const timestamp = block.timestamp ? new Date(block.timestamp * 1000).toUTCString() : null;

      return (
        <div>
          <div className="card">
            <h2>Block #{block.block_height || '?'}</h2>
            <div style={{fontSize:12,color:'var(--text-dim)',wordBreak:'break-all',margin:'8px 0 4px',fontFamily:'monospace'}}>
              {block.block_hash}
            </div>
            {timestamp && <div style={{fontSize:12,color:'var(--text-muted)',marginBottom:12}}>&#128339; {timestamp}</div>}
            <div className="stat-grid">
              <StatBox value={block.tx_count} label="Transactions" />
              <StatBox value={summary.flagged_transactions||0} label="Flagged" color="var(--red)" />
              <StatBox value={feeStats.median_sat_vb||0} label="Median Fee" />
              <StatBox value={feeStats.mean_sat_vb||0} label="Mean Fee" />
              <StatBox value={feeStats.min_sat_vb||0} label="Min Fee" />
              <StatBox value={feeStats.max_sat_vb||0} label="Max Fee" />
            </div>
          </div>

          <div className="dash-grid">
            {Object.keys(classDist).length > 0 && (
              <div className="card">
                <h3>Classifications</h3>
                <DonutChart data={classDist} colorMap={CLS_COLORS} total={block.tx_count} />
              </div>
            )}
            {Object.keys(hCounts).length > 0 && (
              <div className="card">
                <h3>Heuristic Detections</h3>
                <HeuristicBars counts={hCounts} total={block.tx_count} heuristics={summary.heuristics_applied||[]} />
              </div>
            )}
          </div>

          {Object.keys(scriptDist).length > 0 && (
            <div className="card">
              <h3>Script Types</h3>
              <ScriptTypeBar dist={scriptDist} />
            </div>
          )}

          {!hasTxs && (
            <div className="card empty-state">
              <div className="icon">&#128196;</div>
              <p>Transaction-level details are available for the first block only. Select Block #0 to explore individual transactions.</p>
            </div>
          )}
        </div>
      );
    }

    /* ===================== TRANSACTION EXPLORER ===================== */
    function TransactionExplorer({ data, selBlock, setSelBlock }) {
      const blocks = data.blocks || [];

      // Find blocks with tx data
      const txBlocks = blocks.map((b,i) => ({...b, idx: i})).filter(b => (b.transactions||[]).length > 0);

      if (txBlocks.length === 0) {
        return (
          <div className="card empty-state">
            <div className="icon">&#128176;</div>
            <p>No transaction-level data available.</p>
          </div>
        );
      }

      const block = txBlocks[0];
      const txs = block.transactions || [];

      return <TransactionList txs={txs} blockHeight={block.block_height} />;
    }

    function TransactionList({ txs, blockHeight }) {
      const [search, setSearch] = useState('');
      const [classFilter, setClassFilter] = useState('all');
      const [heurFilter, setHeurFilter] = useState('all');
      const [flaggedOnly, setFlaggedOnly] = useState(false);
      const [expandedTx, setExpandedTx] = useState(null);
      const [page, setPage] = useState(0);
      const PAGE_SIZE = 50;

      const heurIds = useMemo(() => {
        if (txs.length === 0) return [];
        return Object.keys(txs[0].heuristics || {});
      }, [txs]);

      const classifications = useMemo(() => {
        const s = new Set(txs.map(t => t.classification));
        return Array.from(s).sort();
      }, [txs]);

      const classCounts = useMemo(() => {
        const c = {};
        txs.forEach(t => { c[t.classification] = (c[t.classification]||0) + 1; });
        return c;
      }, [txs]);

      const filtered = useMemo(() => {
        return txs.filter(tx => {
          if (search && !tx.txid.toLowerCase().includes(search.toLowerCase())) return false;
          if (classFilter !== 'all' && tx.classification !== classFilter) return false;
          if (heurFilter !== 'all') {
            const h = (tx.heuristics||{})[heurFilter];
            if (!h || !h.detected) return false;
          }
          if (flaggedOnly) {
            if (!Object.values(tx.heuristics||{}).some(h => h.detected)) return false;
          }
          return true;
        });
      }, [txs, search, classFilter, heurFilter, flaggedOnly]);

      const pageCount = Math.ceil(filtered.length / PAGE_SIZE);
      const pageTxs = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
      useEffect(() => { setPage(0); }, [search, classFilter, heurFilter, flaggedOnly]);

      return (
        <div>
          <div className="card">
            <div className="card-header">
              <h2>&#128176; Transactions — Block #{blockHeight}</h2>
              <span style={{color:'var(--text-muted)',fontSize:13}}>{fmtNum(filtered.length)} of {fmtNum(txs.length)}</span>
            </div>

            {/* Classification pills */}
            <div style={{display:'flex',flexWrap:'wrap',gap:6,marginBottom:14}}>
              {Object.entries(classCounts).sort((a,b) => b[1]-a[1]).map(([cls, count]) => (
                <span key={cls}
                  className={`badge ${(CLS_COLORS[cls]||{}).cls||'badge-blue'}`}
                  style={{cursor:'pointer', opacity: classFilter !== 'all' && classFilter !== cls ? 0.4 : 1}}
                  onClick={() => setClassFilter(classFilter === cls ? 'all' : cls)}>
                  {cls.replace(/_/g,' ')}: {fmtNum(count)}
                </span>
              ))}
            </div>

            {/* Filter bar */}
            <div className="filter-bar">
              <input type="text" placeholder="&#128269; Search by txid..." value={search}
                onChange={e => setSearch(e.target.value)} />
              <select value={classFilter} onChange={e => setClassFilter(e.target.value)}>
                <option value="all">All classifications</option>
                {classifications.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
              <select value={heurFilter} onChange={e => setHeurFilter(e.target.value)}>
                <option value="all">All heuristics</option>
                {heurIds.map(h => <option key={h} value={h}>{h.replace(/_/g,' ')}</option>)}
              </select>
              <button className={`btn ${flaggedOnly ? 'active' : ''}`}
                onClick={() => setFlaggedOnly(!flaggedOnly)}>
                &#9873; Flagged only
              </button>
            </div>

            {/* Transaction table */}
            <div style={{overflowX:'auto'}}>
              <table>
                <thead>
                  <tr>
                    <th style={{width:40}}>#</th>
                    <th>TXID</th>
                    <th>Classification</th>
                    <th>In/Out</th>
                    <th>Fee Rate</th>
                    <th>Heuristics</th>
                  </tr>
                </thead>
                <tbody>
                  {pageTxs.map((tx, i) => {
                    const idx = page * PAGE_SIZE + i;
                    const detected = Object.entries(tx.heuristics||{}).filter(([,v]) => v.detected).map(([k]) => k);
                    const isExp = expandedTx === tx.txid;

                    return (
                      <React.Fragment key={tx.txid}>
                        <tr className={`tx-row ${isExp ? 'expanded' : ''}`}
                          onClick={() => setExpandedTx(isExp ? null : tx.txid)}>
                          <td style={{color:'var(--text-dim)'}}>{idx}</td>
                          <td style={{fontFamily:'monospace',fontSize:12}}>
                            {tx.txid.substring(0,12)}...{tx.txid.substring(56)}
                          </td>
                          <td>
                            <span className={`badge ${(CLS_COLORS[tx.classification]||{}).cls||'badge-blue'}`}>
                              {tx.classification}
                            </span>
                          </td>
                          <td style={{fontSize:12,color:'var(--text-muted)'}}>
                            {tx.input_count != null ? `${tx.input_count} → ${tx.output_count}` : '—'}
                          </td>
                          <td style={{fontSize:12,color:'var(--text-muted)'}}>
                            {tx.fee_rate_sat_vb != null ? `${tx.fee_rate_sat_vb} sat/vB` : tx.is_coinbase ? 'coinbase' : '—'}
                          </td>
                          <td>
                            {detected.length > 0 ? (
                              detected.slice(0,3).map(h => (
                                <span key={h} className="badge badge-red" style={{marginRight:3,fontSize:10}}>{h}</span>
                              ))
                            ) : (
                              <span style={{color:'var(--text-dim)',fontSize:11}}>none</span>
                            )}
                            {detected.length > 3 && <span style={{color:'var(--text-dim)',fontSize:11}}>+{detected.length-3}</span>}
                          </td>
                        </tr>
                        {isExp && (
                          <tr><td colSpan={6} style={{padding:0}}><TxDetail tx={tx} /></td></tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {pageCount > 1 && (
              <div className="pagination">
                <button className="btn" disabled={page===0} onClick={() => setPage(p => p-1)}>&#8592; Prev</button>
                <span style={{color:'var(--text-muted)',fontSize:13}}>Page {page+1} of {pageCount}</span>
                <button className="btn" disabled={page>=pageCount-1} onClick={() => setPage(p => p+1)}>Next &#8594;</button>
              </div>
            )}
          </div>
        </div>
      );
    }

    /* ===================== TX DETAIL ===================== */
    function TxDetail({ tx }) {
      const heuristics = tx.heuristics || {};

      return (
        <div className="tx-detail">
          <div style={{fontFamily:'monospace',fontSize:11,wordBreak:'break-all',color:'var(--text-dim)',marginBottom:14}}>
            TXID: {tx.txid}
          </div>

          <div className="tx-detail-grid">
            {/* Left: Metadata + Flow */}
            <div>
              <div style={{marginBottom:12}}>
                Classification: <span className={`badge ${(CLS_COLORS[tx.classification]||{}).cls||'badge-blue'}`}>{tx.classification}</span>
              </div>
              {tx.input_count != null && (
                <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8,marginBottom:12}}>
                  <div className="stat-box" style={{padding:8}}>
                    <div className="value" style={{fontSize:18,color:'var(--accent)'}}>{tx.input_count}</div>
                    <div className="label">Inputs</div>
                  </div>
                  <div className="stat-box" style={{padding:8}}>
                    <div className="value" style={{fontSize:18,color:'var(--green)'}}>{tx.output_count}</div>
                    <div className="label">Outputs</div>
                  </div>
                </div>
              )}
              {tx.fee_rate_sat_vb != null && (
                <div style={{fontSize:12,color:'var(--text-muted)',marginBottom:8}}>
                  Fee Rate: <strong style={{color:'var(--text)'}}>{tx.fee_rate_sat_vb} sat/vB</strong>
                </div>
              )}
              {tx.total_output_value_sats != null && (
                <div style={{fontSize:12,color:'var(--text-muted)',marginBottom:8}}>
                  Total Output: <strong style={{color:'var(--text)'}}>{fmtSats(tx.total_output_value_sats)}</strong>
                </div>
              )}
              {/* Transaction Flow Diagram */}
              {tx.input_count != null && <TxFlowDiagram inputs={tx.input_count} outputs={tx.output_count} classification={tx.classification} isCoinbase={tx.is_coinbase} />}
            </div>

            {/* Right: Heuristic results */}
            <div>
              <h3 style={{marginBottom:10}}>Heuristic Results</h3>
              <div className="heuristic-grid">
                {Object.entries(heuristics).map(([id, result]) => (
                  <div key={id} className={`heuristic-item ${result.detected ? 'detected' : 'not-detected'}`}>
                    <span className={`dot ${result.detected ? 'on' : 'off'}`} />
                    <span style={{fontWeight:500}}>{id.replace(/_/g,' ')}</span>
                    {result.detected && result.confidence && (
                      <span className={`badge badge-${result.confidence==='high'?'green':result.confidence==='medium'?'orange':'red'}`}
                        style={{fontSize:10,marginLeft:'auto'}}>{result.confidence}</span>
                    )}
                  </div>
                ))}
              </div>
              {heuristics.change_detection && heuristics.change_detection.detected && (
                <div style={{marginTop:10,fontSize:12,padding:'8px 10px',background:'var(--surface)',borderRadius:6}}>
                  <strong>Change Detection:</strong> output #{heuristics.change_detection.likely_change_index},
                  method: <em>{heuristics.change_detection.method}</em>,
                  confidence: <span className={`badge badge-${heuristics.change_detection.confidence==='high'?'green':'orange'}`} style={{fontSize:10}}>{heuristics.change_detection.confidence}</span>
                </div>
              )}
              {heuristics.op_return && heuristics.op_return.detected && (
                <div style={{marginTop:8,fontSize:12,padding:'8px 10px',background:'var(--surface)',borderRadius:6}}>
                  <strong>OP_RETURN:</strong> data embedded in transaction
                </div>
              )}
            </div>
          </div>
        </div>
      );
    }

    /* ===================== TX FLOW DIAGRAM ===================== */
    function TxFlowDiagram({ inputs, outputs, classification, isCoinbase }) {
      const maxIO = Math.max(inputs, outputs, 1);
      const rowH = 22;
      const padY = 14;
      const h = maxIO * rowH + padY * 2;
      const w = 320;
      const txBoxW = 100;
      const txBoxH = 32;
      const txBoxX = (w - txBoxW) / 2;
      const txBoxY = h / 2 - txBoxH / 2;
      const clsColor = (CLS_COLORS[classification]||{}).hex || '#8b949e';

      const inCount = isCoinbase ? 1 : inputs;
      const inStartY = h / 2 - (inCount - 1) * rowH / 2;
      const outStartY = h / 2 - (outputs - 1) * rowH / 2;

      return (
        <div className="tx-flow">
          <svg width={w} height={h} style={{display:'block'}}>
            {/* Input lines */}
            {Array.from({length: inCount}, (_, i) => {
              const y = inStartY + i * rowH;
              return (
                <g key={`i${i}`}>
                  <line x1={24} y1={y} x2={txBoxX} y2={h/2} className="flow-input-line" />
                  <circle cx={20} cy={y} r={4} className="flow-dot-in" />
                  <text x={8} y={y+4} fontSize={9} fill="var(--text-dim)" textAnchor="middle">{isCoinbase && i===0 ? 'CB' : ''}</text>
                </g>
              );
            })}

            {/* TX box */}
            <rect x={txBoxX} y={txBoxY} width={txBoxW} height={txBoxH} className="flow-tx-box"
              style={{stroke: clsColor, strokeWidth: 1.5}} />
            <text x={w/2} y={h/2+4} textAnchor="middle" fontSize={11} fontWeight="600" fill={clsColor}>
              {classification.replace(/_/g,' ').substring(0,14)}
            </text>

            {/* Output lines */}
            {Array.from({length: outputs}, (_, i) => {
              const y = outStartY + i * rowH;
              return (
                <g key={`o${i}`}>
                  <line x1={txBoxX + txBoxW} y1={h/2} x2={w-24} y2={y} className="flow-output-line" />
                  <circle cx={w-20} cy={y} r={4} className="flow-dot-out" />
                </g>
              );
            })}

            {/* Labels */}
            <text x={4} y={12} fontSize={10} fill="var(--text-dim)">Inputs ({inCount})</text>
            <text x={w-4} y={12} fontSize={10} fill="var(--text-dim)" textAnchor="end">Outputs ({outputs})</text>
          </svg>
        </div>
      );
    }

    ReactDOM.createRoot(document.getElementById('root')).render(<App />);
  </script>
</body>
</html>
'''


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def main():
    raw_port = os.environ.get('PORT', '3000')
    try:
        port = int(raw_port)
    except ValueError:
        port = 3000
    if port <= 0 or port > 65535:
        port = 3000

    server = ReusableTCPServer(('0.0.0.0', port), SherlockHandler)

    # Handle graceful shutdown
    def shutdown_handler(sig, frame):
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # Print URL to stdout (required by web.sh spec)
    print(f'http://127.0.0.1:{port}', flush=True)

    server.serve_forever()


if __name__ == '__main__':
    main()

