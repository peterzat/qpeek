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
        if state.heartbeat_started:
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
    print(f"\n  qpeek ready:  {url}\n", file=sys.stderr)

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
    if ask is not None and state.results:
        if batch:
            print(json.dumps(state.results, indent=None))
        else:
            print(json.dumps(state.results[0], indent=None))

    return exit_code
