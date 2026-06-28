"""Browser-based inference studio for writer-model."""

import argparse
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from writer_model.api import WriterEditor

# ---------------------------------------------------------------------------
# HTML / CSS / JS — fully self-contained, no CDN required
# ---------------------------------------------------------------------------

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Writer Studio</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg: #080808;
    --surface: #111111;
    --surface2: #191919;
    --border: #252525;
    --border-focus: #444;
    --text: #e8e8e8;
    --muted: #666;
    --accent: #c8ff00;
    --accent-dim: rgba(200,255,0,0.08);
    --danger: #ff4444;
    --radius: 10px;
    --font-mono: "JetBrains Mono", "Fira Code", "SF Mono", Menlo, monospace;
    --font-ui: -apple-system, BlinkMacSystemFont, "Inter", sans-serif;
  }

  html, body {
    height: 100%;
    background: var(--bg);
    color: var(--text);
    font-family: var(--font-ui);
    font-size: 14px;
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
  }

  /* ── Layout ── */
  .app {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    max-width: 1100px;
    margin: 0 auto;
    padding: 40px 24px 80px;
  }

  /* ── Header ── */
  header {
    display: flex;
    align-items: baseline;
    gap: 10px;
    margin-bottom: 40px;
  }
  .logo {
    font-size: 18px;
    font-weight: 600;
    letter-spacing: -0.3px;
    color: var(--text);
  }
  .logo span { color: var(--accent); }
  .tagline {
    font-size: 12px;
    color: var(--muted);
    letter-spacing: 0.02em;
  }

  /* ── Input grid ── */
  .inputs {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-bottom: 20px;
  }
  @media (max-width: 640px) { .inputs { grid-template-columns: 1fr; } }

  .field { display: flex; flex-direction: column; gap: 8px; }

  label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted);
  }

  textarea {
    width: 100%;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text);
    font-family: var(--font-mono);
    font-size: 13px;
    line-height: 1.65;
    padding: 14px 16px;
    resize: vertical;
    outline: none;
    transition: border-color 0.15s, box-shadow 0.15s;
  }
  textarea:focus {
    border-color: var(--border-focus);
    box-shadow: 0 0 0 3px rgba(255,255,255,0.04);
  }
  textarea::placeholder { color: #383838; }
  #context-input  { min-height: 180px; }
  #draft-input    { min-height: 180px; }

  /* ── Controls row ── */
  .controls {
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 32px;
    flex-wrap: wrap;
  }

  .btn-generate {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: var(--accent);
    color: #000;
    border: none;
    border-radius: 8px;
    font-family: var(--font-ui);
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 0.01em;
    padding: 10px 24px;
    cursor: pointer;
    transition: opacity 0.15s, transform 0.1s;
    user-select: none;
  }
  .btn-generate:hover:not(:disabled) { opacity: 0.88; }
  .btn-generate:active:not(:disabled) { transform: scale(0.97); }
  .btn-generate:disabled { opacity: 0.4; cursor: not-allowed; }

  .spinner {
    width: 14px; height: 14px;
    border: 2px solid rgba(0,0,0,0.3);
    border-top-color: #000;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
    display: none;
  }
  .btn-generate.loading .spinner { display: block; }
  .btn-generate.loading .arrow { display: none; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .param-group {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-left: auto;
  }
  .param-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .param-input {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text);
    font-family: var(--font-ui);
    font-size: 13px;
    padding: 5px 10px;
    width: 64px;
    outline: none;
    text-align: center;
  }
  .param-input:focus { border-color: var(--border-focus); }

  /* ── Output section ── */
  #output-section { display: none; flex-direction: column; gap: 12px; }
  #output-section.visible { display: flex; }

  .output-header {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .output-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .output-count {
    font-size: 11px;
    color: #3a3a3a;
  }

  .cards { display: flex; flex-direction: column; gap: 10px; }

  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    position: relative;
    transition: border-color 0.15s;
    cursor: default;
  }
  .card.selected {
    border-color: var(--accent);
    background: var(--accent-dim);
  }
  .card:hover { border-color: #333; }
  .card.selected:hover { border-color: var(--accent); }

  .card-index {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 12px;
  }
  .card.selected .card-index { color: var(--accent); }

  .card-text {
    font-family: var(--font-mono);
    font-size: 14px;
    line-height: 1.7;
    color: var(--text);
    white-space: pre-wrap;
    word-break: break-word;
  }

  .card-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 14px;
  }

  .char-count {
    font-size: 11px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }

  .btn-copy {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--muted);
    font-family: var(--font-ui);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.04em;
    padding: 4px 10px;
    cursor: pointer;
    transition: border-color 0.15s, color 0.15s;
  }
  .btn-copy:hover { border-color: #444; color: var(--text); }
  .btn-copy.copied { border-color: var(--accent); color: var(--accent); }

  /* ── Error bar ── */
  .error-bar {
    display: none;
    background: rgba(255,68,68,0.08);
    border: 1px solid rgba(255,68,68,0.25);
    border-radius: var(--radius);
    color: #ff8888;
    font-size: 13px;
    padding: 12px 16px;
    margin-bottom: 16px;
  }
  .error-bar.visible { display: block; }

  /* ── Toast ── */
  .toast {
    position: fixed;
    bottom: 32px;
    left: 50%;
    transform: translateX(-50%) translateY(20px);
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    font-size: 13px;
    padding: 10px 18px;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.2s, transform 0.2s;
    white-space: nowrap;
  }
  .toast.show {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }

  /* ── Divider ── */
  .divider {
    height: 1px;
    background: var(--border);
    margin: 28px 0;
  }
</style>
</head>
<body>
<div class="app">

  <header>
    <div class="logo">writer<span>.</span>studio</div>
    <div class="tagline">local inference · your voice, any draft</div>
  </header>

  <div class="inputs">
    <div class="field">
      <label for="context-input">Context</label>
      <textarea
        id="context-input"
        placeholder="Paste the context — what this is about, source material, links, notes…"
        spellcheck="false"
      ></textarea>
    </div>
    <div class="field">
      <label for="draft-input">Draft</label>
      <textarea
        id="draft-input"
        placeholder="Paste the rough draft — the raw text to rewrite into your voice…"
        spellcheck="false"
      ></textarea>
    </div>
  </div>

  <div class="controls">
    <button class="btn-generate" id="generate-btn" onclick="generate()">
      <div class="spinner"></div>
      <span class="arrow">Generate →</span>
    </button>

    <div class="param-group">
      <span class="param-label">n</span>
      <input class="param-input" id="param-n" type="number" min="1" max="8" value="1">
      <span class="param-label" style="margin-left:6px">temp</span>
      <input class="param-input" id="param-temp" type="number" min="0" max="2" step="0.05" value="0.7">
    </div>
  </div>

  <div class="error-bar" id="error-bar"></div>

  <div id="output-section">
    <div class="output-header">
      <span class="output-label">Output</span>
      <span class="output-count" id="output-count"></span>
    </div>
    <div class="cards" id="cards"></div>
  </div>

</div>

<div class="toast" id="toast">Copied to clipboard</div>

<script>
let lastOutputs = [];

async function generate() {
  const context = document.getElementById('context-input').value.trim();
  const draft   = document.getElementById('draft-input').value.trim();
  const n       = parseInt(document.getElementById('param-n').value) || 1;
  const temp    = parseFloat(document.getElementById('param-temp').value) || 0.7;

  hideError();

  if (!context || !draft) {
    showError('Both context and draft are required.');
    return;
  }

  setLoading(true);

  try {
    const res = await fetch('/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ context, draft, n, temp }),
    });
    if (!res.ok) {
      const err = await res.text();
      throw new Error(err || `HTTP ${res.status}`);
    }
    const data = await res.json();
    lastOutputs = data.outputs || [];
    renderOutputs(lastOutputs);
  } catch (e) {
    showError(e.message || 'Generation failed. Check the terminal for details.');
  } finally {
    setLoading(false);
  }
}

function renderOutputs(outputs) {
  const section = document.getElementById('output-section');
  const cards   = document.getElementById('cards');
  const count   = document.getElementById('output-count');

  cards.innerHTML = '';
  count.textContent = outputs.length > 1 ? `${outputs.length} candidates` : '';

  outputs.forEach((text, i) => {
    const card = document.createElement('div');
    card.className = 'card' + (i === 0 ? ' selected' : '');
    card.dataset.index = i;
    card.onclick = () => selectCard(i);

    const len = text.length;

    card.innerHTML = `
      <div class="card-index">${outputs.length > 1 ? `Candidate ${i + 1}` : 'Result'}</div>
      <div class="card-text">${escHtml(text)}</div>
      <div class="card-footer">
        <span class="char-count">${len} chars</span>
        <button class="btn-copy" onclick="copyCard(event, ${i})">Copy</button>
      </div>
    `;
    cards.appendChild(card);
  });

  section.classList.add('visible');
}

function selectCard(index) {
  document.querySelectorAll('.card').forEach((c, i) => {
    c.classList.toggle('selected', i === index);
  });
}

function copyCard(event, index) {
  event.stopPropagation();
  const text = lastOutputs[index];
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => {
    const btn = event.currentTarget;
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 1800);
    showToast('Copied to clipboard');
  });
}

function setLoading(on) {
  const btn = document.getElementById('generate-btn');
  btn.disabled = on;
  btn.classList.toggle('loading', on);
}

function showError(msg) {
  const bar = document.getElementById('error-bar');
  bar.textContent = msg;
  bar.classList.add('visible');
}

function hideError() {
  document.getElementById('error-bar').classList.remove('visible');
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2000);
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// Submit on Cmd/Ctrl+Enter from either textarea
document.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
    e.preventDefault();
    generate();
  }
});
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class StudioHandler(BaseHTTPRequestHandler):
    editor: WriterEditor = None

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/generate":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length))
            context = payload["context"]
            draft = payload["draft"]
            n = max(1, int(payload.get("n", 1)))
            temp = float(payload.get("temp", 0.7))
        except Exception as exc:
            self._json_error(400, f"bad request: {exc}")
            return

        try:
            result = self.editor.edit(
                context, draft, n=n, temp=temp, source="studio"
            )
        except Exception as exc:
            self._json_error(500, str(exc))
            return

        self._json_ok({"outputs": result.outputs, "chosen": result.chosen_output})

    def _json_ok(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_error(self, code, msg):
        body = json.dumps({"error": msg}).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="Launch the writer-model browser studio.")
    ap.add_argument("--port", type=int, default=7860)
    ap.add_argument("--adapter", default=None)
    ap.add_argument("--base-model", default=None)
    ap.add_argument("--no-open", action="store_true", help="don't open browser automatically")
    args = ap.parse_args(argv)

    print("writer-model-studio: loading model…")
    editor = WriterEditor(adapter_path=args.adapter, base_model=args.base_model)
    editor.load()
    StudioHandler.editor = editor

    url = f"http://localhost:{args.port}"
    print(f"Studio ready → {url}  (Ctrl+C to quit)")
    if not args.no_open:
        webbrowser.open(url)

    server = HTTPServer(("", args.port), StudioHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStudio stopped.")


if __name__ == "__main__":
    main()
