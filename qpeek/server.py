"""HTTP server for qpeek."""
import html as html_mod
import json
import mimetypes
import os
import signal
import sys
import threading
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

from qpeek.cli import file_type
from qpeek.html_gen import generate_page
from qpeek.markdown import render_markdown


class QpeekState:
    """Shared mutable state for the server."""

    def __init__(self, files, ask, choices, batch, group, custom_html, timeout):
        self.files = files
        self.ask = ask
        self.choices = choices
        self.batch = batch
        self.group = group
        self.custom_html = custom_html
        self.timeout = timeout

        # Batch state
        if batch:
            if group > 1:
                self.batch_items = [files[i:i + group] for i in range(0, len(files), group)]
            else:
                self.batch_items = [[f] for f in files]
            self.batch_total = len(self.batch_items)
        else:
            self.batch_items = [files]
            self.batch_total = 1
        self.batch_index = 0

        # Results collection
        self.results = []  # list of dicts for batch mode
        self.completed = False
        self.abandoned = False
        self.exit_code = 0
        self.shutdown_event = threading.Event()
        self.last_activity = time.monotonic()
        self.last_heartbeat = time.monotonic()
        self.heartbeat_started = False

    def current_files(self):
        """Return the file list for the current batch step."""
        if self.batch_index < len(self.batch_items):
            return self.batch_items[self.batch_index]
        return []

    def current_basenames(self):
        return [os.path.basename(f) for f in self.current_files()]

    def advance(self):
        """Move to next batch item. Return True if there are more items."""
        self.batch_index += 1
        return self.batch_index < self.batch_total

    def file_key(self):
        """Return the file/files key-value for JSON output."""
        basenames = self.current_basenames()
        if len(basenames) == 1:
            return {"file": basenames[0]}
        return {"files": basenames}

    def record_submit(self, data):
        """Record a submission from the browser."""
        entry = self.file_key()
        if "choice" in data:
            entry["choice"] = data["choice"]
        elif "response" in data:
            entry["response"] = data["response"]
        self.results.append(entry)

    def record_close(self):
        """Record a close (view-only) from the browser."""
        # In view-only batch mode, no data to record
        pass


def _build_file_contents(state):
    """Pre-render markdown and text file contents for the current batch step."""
    contents = {}
    for fpath in state.current_files():
        bn = os.path.basename(fpath)
        ft = file_type(bn)
        if ft == "markdown":
            with open(fpath, "r", errors="replace") as f:
                contents[bn] = render_markdown(f.read())
        elif ft == "text":
            with open(fpath, "r", errors="replace") as f:
                contents[bn] = html_mod.escape(f.read())
    return contents


class QpeekHandler(BaseHTTPRequestHandler):
    """HTTP request handler for qpeek."""

    def log_message(self, format, *args):
        # Send logs to stderr, not stdout
        print(f"qpeek: {format % args}", file=sys.stderr)

    def do_GET(self):
        state = self.server.qpeek_state
        state.last_activity = time.monotonic()

        if self.path == "/":
            self._serve_index(state)
        elif self.path.startswith("/files/"):
            self._serve_file(state)
        elif self.path == "/qpeek/meta":
            self._serve_meta(state)
        elif self.path == "/qpeek/heartbeat":
            self._handle_heartbeat(state)
        else:
            self.send_error(404)

    def do_POST(self):
        state = self.server.qpeek_state
        state.last_activity = time.monotonic()

        if self.path == "/qpeek/close":
            self._handle_close(state)
        elif self.path == "/qpeek/submit":
            self._handle_submit(state)
        else:
            self.send_error(404)

    def _serve_index(self, state):
        if state.custom_html:
            with open(state.custom_html, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        file_contents = _build_file_contents(state)
        page = generate_page(
            files=state.current_files(),
            ask=state.ask,
            choices=state.choices,
            batch=state.batch,
            group=state.group,
            batch_index=state.batch_index,
            batch_total=state.batch_total,
            file_contents=file_contents,
        )
        content = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache, no-store")
        self.end_headers()
        self.wfile.write(content)

    def _serve_file(self, state):
        name = self.path[len("/files/"):]
        # Find the file by basename match across all files
        target = None
        for fpath in state.files:
            if os.path.basename(fpath) == name:
                target = fpath
                break
        if not target or not os.path.isfile(target):
            self.send_error(404)
            return

        mime, _ = mimetypes.guess_type(target)
        if mime is None:
            mime = "application/octet-stream"
        with open(target, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_meta(self, state):
        meta = {
            "files": state.current_basenames(),
        }
        if state.ask:
            meta["question"] = state.ask
        if state.choices:
            meta["choices"] = state.choices
        if state.batch:
            meta["batch_index"] = state.batch_index
            meta["batch_total"] = state.batch_total
        body = json.dumps(meta).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_heartbeat(self, state):
        state.last_heartbeat = time.monotonic()
        state.heartbeat_started = True
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_request(self, code="-", size="-"):
        # Suppress heartbeat logging to keep stderr clean
        if self.path == "/qpeek/heartbeat":
            return
        super().log_request(code, size)

    def _handle_close(self, state):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

        state.record_close()
        if state.batch and state.advance():
            return  # more items, browser will reload
        state.completed = True
        state.shutdown_event.set()

    def _handle_submit(self, state):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = {}

        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

        state.record_submit(data)
        if state.batch and state.advance():
            return  # more items, browser will reload
        state.completed = True
        state.shutdown_event.set()


def _timeout_watcher(state):
    """Background thread that checks for inactivity timeout and heartbeat loss."""
    HEARTBEAT_TIMEOUT = 10  # seconds without heartbeat = abandoned
    while not state.shutdown_event.is_set():
        now = time.monotonic()
        # Check inactivity timeout
        if state.timeout > 0:
            elapsed = now - state.last_activity
            if elapsed >= state.timeout:
                state.exit_code = 3
                state.shutdown_event.set()
                return
        # Check heartbeat (only after browser has started sending them)
        # --timeout 0 disables both inactivity and heartbeat abandonment
        if state.heartbeat_started and state.timeout != 0:
            since_heartbeat = now - state.last_heartbeat
            if since_heartbeat >= HEARTBEAT_TIMEOUT:
                state.abandoned = True
                state.exit_code = 1
                state.shutdown_event.set()
                return
        state.shutdown_event.wait(timeout=2)


def _get_tailscale_ip():
    """Get the Tailscale IPv4 address, fall back to hostname."""
    import socket
    import subprocess
    try:
        result = subprocess.run(
            ["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=2
        )
        ip = result.stdout.strip()
        if ip:
            return ip
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return socket.gethostname()


def run_server(files, port, ask, choices, batch, group, custom_html, timeout):
    """Start the server, block until shutdown, return exit code."""
    state = QpeekState(files, ask, choices, batch, group, custom_html, timeout)

    server = ThreadingHTTPServer(("0.0.0.0", port), QpeekHandler)
    server.qpeek_state = state

    # Handle Ctrl-C (only works from main thread)
    def sigint_handler(sig, frame):
        state.abandoned = True
        state.exit_code = 1
        state.shutdown_event.set()

    try:
        signal.signal(signal.SIGINT, sigint_handler)
    except ValueError:
        pass  # not main thread (e.g., during testing)

    # Start timeout/heartbeat watcher
    watcher = threading.Thread(target=_timeout_watcher, args=(state,), daemon=True)
    watcher.start()

    # Serve in a thread so we can wait on the shutdown event
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    ip = _get_tailscale_ip()
    url = f"http://{ip}:{port}"
    print(f"\n  qpeek ready:  {url}\n", file=sys.stderr, flush=True)

    state.shutdown_event.wait()

    server.shutdown()

    # Determine exit code
    if state.exit_code == 3:
        exit_code = 3
    elif state.completed:
        exit_code = 0
    else:
        exit_code = 1

    # Print results to stdout (complete or partial)
    if state.results:
        if batch:
            print(json.dumps(state.results, indent=None))
        else:
            print(json.dumps(state.results[0], indent=None))

    return exit_code


# --- Serve mode: static file server for HTML files and directories ---

class ServeState:
    """Shared state for serve mode."""

    def __init__(self, doc_root, index_file, timeout):
        self.doc_root = doc_root
        self.index_file = index_file  # absolute path, or None for directory listing
        self.timeout = timeout
        self.exit_code = 0
        self.shutdown_event = threading.Event()
        self.last_activity = time.monotonic()

    def touch(self):
        self.last_activity = time.monotonic()


def _serve_timeout_watcher(state):
    """Background thread for serve mode inactivity timeout."""
    while not state.shutdown_event.is_set():
        if state.timeout > 0:
            elapsed = time.monotonic() - state.last_activity
            if elapsed >= state.timeout:
                state.exit_code = 3
                state.shutdown_event.set()
                return
        state.shutdown_event.wait(timeout=2)


def _directory_listing_html(dir_path, url_path):
    """Generate a simple directory listing page."""
    import html as h
    entries = sorted(os.listdir(dir_path))
    dirs = []
    files = []
    for name in entries:
        full = os.path.join(dir_path, name)
        if os.path.isdir(full):
            dirs.append(name)
        elif os.path.isfile(full):
            files.append(name)

    # Build relative URL prefix
    if url_path.endswith("/"):
        prefix = url_path
    else:
        prefix = url_path + "/"

    lines = []
    # Parent link (if not root)
    if url_path not in ("", "/"):
        parent = "/".join(url_path.rstrip("/").split("/")[:-1]) or "/"
        lines.append(f'<li><a href="{h.escape(parent)}">../</a></li>')
    for d in dirs:
        href = prefix + d + "/"
        lines.append(f'<li><a href="{h.escape(href)}">{h.escape(d)}/</a></li>')
    for f in files:
        href = prefix + f
        lines.append(f'<li><a href="{h.escape(href)}">{h.escape(f)}</a></li>')

    title = h.escape(url_path or "/")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Index of {title}</title>
<style>
body {{ background: #1a1a2e; color: #e0e0e0; font-family: -apple-system, BlinkMacSystemFont,
"Segoe UI", Roboto, Helvetica, Arial, sans-serif; padding: 24px; padding-bottom: 80px; }}
h1 {{ font-size: 20px; margin-bottom: 16px; }}
ul {{ list-style: none; padding: 0; }}
li {{ padding: 4px 0; }}
a {{ color: #7ec8e3; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
</style></head>
<body><h1>Index of {title}</h1><ul>{"".join(lines)}</ul>
{_CLOSE_BUTTON_HTML}</body></html>"""


_CLOSE_BUTTON_HTML = """<div id="qpeek-close" style="position:fixed;bottom:16px;right:16px;z-index:999999;">
<button onclick="fetch('/qpeek/close',{method:'POST'}).then(function(){try{window.close();}catch(e){}document.body.innerHTML='<p style=\\'text-align:center;margin-top:40vh;font:18px sans-serif;color:#888\\'>You may close this tab.</p>';})" style="background:#e94560;color:#fff;border:none;border-radius:6px;padding:10px 24px;font-size:15px;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,0.3);min-width:44px;min-height:44px;">Close</button>
</div>"""


class ServeHandler(BaseHTTPRequestHandler):
    """HTTP handler for serve mode: static file server."""

    def log_message(self, format, *args):
        print(f"qpeek: {format % args}", file=sys.stderr)

    def _resolve_path(self):
        """Parse and validate the request path. Return fs_path or None (error already sent)."""
        from urllib.parse import unquote
        state = self.server.serve_state
        path = unquote(self.path.split("?")[0].split("#")[0])

        parts = [p for p in path.split("/") if p and p != "."]
        if any(p == ".." for p in parts):
            self.send_error(403)
            return None, None

        fs_path = os.path.realpath(os.path.join(state.doc_root, *parts))

        if not fs_path.startswith(os.path.realpath(state.doc_root)):
            self.send_error(403)
            return None, None

        if path in ("", "/") and state.index_file:
            fs_path = state.index_file

        return fs_path, path

    def do_GET(self):
        state = self.server.serve_state
        state.touch()

        fs_path, url_path = self._resolve_path()
        if fs_path is None:
            return

        if os.path.isdir(fs_path):
            index = os.path.join(fs_path, "index.html")
            if os.path.isfile(index):
                self._serve_static(index, inject_close=True)
            else:
                content = _directory_listing_html(fs_path, url_path).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
        elif os.path.isfile(fs_path):
            mime, _ = mimetypes.guess_type(fs_path)
            inject = mime is not None and mime.startswith("text/html")
            self._serve_static(fs_path, inject_close=inject)
        else:
            self.send_error(404)

    def do_POST(self):
        state = self.server.serve_state
        state.touch()

        if self.path == "/qpeek/close":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
            state.exit_code = 0
            state.shutdown_event.set()
        else:
            self.send_error(404)

    def _serve_static(self, fs_path, inject_close=False):
        mime, _ = mimetypes.guess_type(fs_path)
        if mime is None:
            mime = "application/octet-stream"
        with open(fs_path, "rb") as f:
            data = f.read()
        if inject_close:
            snippet = _CLOSE_BUTTON_HTML.encode("utf-8")
            # Insert before </body> if present, otherwise append
            lower = data.lower()
            idx = lower.rfind(b"</body>")
            if idx != -1:
                data = data[:idx] + snippet + data[idx:]
            else:
                data = data + snippet
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def run_serve_mode(paths, port, timeout):
    """Start a static file server for serve mode. Return exit code."""
    # Determine doc_root and index_file
    if len(paths) == 1 and os.path.isdir(paths[0]):
        doc_root = paths[0]
        index_path = os.path.join(doc_root, "index.html")
        index_file = index_path if os.path.isfile(index_path) else None
    else:
        # HTML file(s): root is the parent directory of the first file
        doc_root = os.path.dirname(paths[0])
        index_file = paths[0]

    state = ServeState(doc_root, index_file, timeout)

    server = ThreadingHTTPServer(("0.0.0.0", port), ServeHandler)
    server.serve_state = state

    def sigint_handler(sig, frame):
        state.exit_code = 1
        state.shutdown_event.set()

    try:
        signal.signal(signal.SIGINT, sigint_handler)
    except ValueError:
        pass

    watcher = threading.Thread(target=_serve_timeout_watcher, args=(state,), daemon=True)
    watcher.start()

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    ip = _get_tailscale_ip()
    url = f"http://{ip}:{port}"
    if index_file and len(paths) == 1 and not os.path.isdir(paths[0]):
        url += f"/{os.path.basename(index_file)}"
    print(f"\n  qpeek serving:  {url}\n", file=sys.stderr, flush=True)

    state.shutdown_event.wait()
    server.shutdown()
    return state.exit_code
