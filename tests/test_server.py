"""Integration tests for the qpeek server."""
import json
import os
import struct
import tempfile
import threading
import time
import zlib
from urllib.request import urlopen, Request

import pytest

from qpeek.server import run_server


def _make_png(path):
    """Create a minimal valid PNG file."""
    raw = b'\x00' + b'\xff\x00\x00' * 2
    raw += b'\x00' + b'\x00\xff\x00' * 2
    compressed = zlib.compress(raw)
    def chunk(ctype, data):
        c = ctype + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    ihdr = struct.pack('>IIBBBBB', 2, 2, 8, 2, 0, 0, 0)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', compressed) + chunk(b'IEND', b'')
    with open(path, 'wb') as f:
        f.write(png)


class ServerRunner:
    """Context manager to run qpeek server in a background thread."""

    def __init__(self, port, **kwargs):
        self.port = port
        self.kwargs = kwargs
        self.exit_code = None
        self._stdout_lines = []
        self._thread = None

    def __enter__(self):
        import sys, io
        self._old_stdout = sys.stdout
        self._capture = io.StringIO()

        def run():
            sys.stdout = self._capture
            self.exit_code = run_server(port=self.port, **self.kwargs)
            sys.stdout = self._old_stdout

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        time.sleep(0.4)
        return self

    def __exit__(self, *args):
        if self._thread:
            self._thread.join(timeout=3)
        import sys
        sys.stdout = self._old_stdout

    @property
    def stdout(self):
        return self._capture.getvalue()

    def get(self, path):
        return urlopen(f"http://127.0.0.1:{self.port}{path}")

    def post(self, path, data=None):
        body = json.dumps(data).encode() if data else None
        headers = {"Content-Type": "application/json"} if data else {}
        req = Request(f"http://127.0.0.1:{self.port}{path}",
                      data=body, headers=headers, method="POST")
        return urlopen(req)


@pytest.fixture
def png_file(tmp_path):
    path = str(tmp_path / "test.png")
    _make_png(path)
    return path


@pytest.fixture
def png_files(tmp_path):
    paths = []
    for name in ("a.png", "b.png", "c.png"):
        path = str(tmp_path / name)
        _make_png(path)
        paths.append(path)
    return paths


@pytest.fixture
def md_file(tmp_path):
    path = str(tmp_path / "test.md")
    path_obj = tmp_path / "test.md"
    path_obj.write_text("# Hello\n\nSome **bold** text.\n")
    return path


@pytest.fixture
def txt_file(tmp_path):
    path = str(tmp_path / "test.txt")
    (tmp_path / "test.txt").write_text("plain text content\n")
    return path


class TestViewMode:
    def test_single_file_view_and_close(self, png_file):
        with ServerRunner(port=2030, files=[png_file], ask=None, choices=None,
                          batch=False, group=1, custom_html=None, timeout=10) as srv:
            resp = srv.get("/")
            html = resp.read().decode()
            assert "test.png" in html
            assert "Close" in html

            srv.post("/qpeek/close")
            time.sleep(0.3)

        assert srv.exit_code == 0
        assert srv.stdout.strip() == ""

    def test_multi_file_view(self, png_files):
        with ServerRunner(port=2031, files=png_files, ask=None, choices=None,
                          batch=False, group=1, custom_html=None, timeout=10) as srv:
            resp = srv.get("/")
            html = resp.read().decode()
            assert "a.png" in html
            assert "b.png" in html
            assert "c.png" in html

            srv.post("/qpeek/close")
            time.sleep(0.3)

        assert srv.exit_code == 0

    def test_markdown_rendering(self, md_file):
        with ServerRunner(port=2032, files=[md_file], ask=None, choices=None,
                          batch=False, group=1, custom_html=None, timeout=10) as srv:
            resp = srv.get("/")
            html = resp.read().decode()
            assert "Hello" in html
            assert "<strong>bold</strong>" in html

            srv.post("/qpeek/close")
            time.sleep(0.3)

        assert srv.exit_code == 0

    def test_text_file_rendering(self, txt_file):
        with ServerRunner(port=2033, files=[txt_file], ask=None, choices=None,
                          batch=False, group=1, custom_html=None, timeout=10) as srv:
            resp = srv.get("/")
            html = resp.read().decode()
            assert "plain text content" in html

            srv.post("/qpeek/close")
            time.sleep(0.3)

        assert srv.exit_code == 0


class TestSurveyChat:
    def test_ask_freeform(self, png_file):
        with ServerRunner(port=2034, files=[png_file], ask="Rate this image",
                          choices=None, batch=False, group=1,
                          custom_html=None, timeout=10) as srv:
            resp = srv.get("/")
            html = resp.read().decode()
            assert "Rate this image" in html
            assert 'type="text"' in html

            srv.post("/qpeek/submit", {"response": "looks good"})
            time.sleep(0.3)

        assert srv.exit_code == 0
        result = json.loads(srv.stdout.strip())
        assert result["file"] == "test.png"
        assert result["response"] == "looks good"


class TestSurveyButtons:
    def test_ask_with_choices(self, png_file):
        with ServerRunner(port=2035, files=[png_file], ask="Rate this",
                          choices=["Good", "Bad"], batch=False, group=1,
                          custom_html=None, timeout=10) as srv:
            resp = srv.get("/")
            html = resp.read().decode()
            assert "Good" in html
            assert "Bad" in html
            assert "<textarea" not in html

            srv.post("/qpeek/submit", {"choice": "Good"})
            time.sleep(0.3)

        assert srv.exit_code == 0
        result = json.loads(srv.stdout.strip())
        assert result["choice"] == "Good"

    def test_multi_file_survey(self, png_files):
        with ServerRunner(port=2036, files=png_files[:2], ask="Which?",
                          choices=["Left", "Right"], batch=False, group=1,
                          custom_html=None, timeout=10) as srv:
            resp = srv.get("/")
            html = resp.read().decode()
            assert "a.png" in html
            assert "b.png" in html

            srv.post("/qpeek/submit", {"choice": "Left"})
            time.sleep(0.3)

        result = json.loads(srv.stdout.strip())
        assert result["files"] == ["a.png", "b.png"]
        assert result["choice"] == "Left"


class TestBatchMode:
    def test_batch_view(self, png_files):
        with ServerRunner(port=2037, files=png_files, ask=None, choices=None,
                          batch=True, group=1, custom_html=None, timeout=10) as srv:
            # Step 1
            html = srv.get("/").read().decode()
            assert "1 / 3" in html
            srv.post("/qpeek/close")
            time.sleep(0.3)

            # Step 2
            html = srv.get("/").read().decode()
            assert "2 / 3" in html
            srv.post("/qpeek/close")
            time.sleep(0.3)

            # Step 3 (last)
            html = srv.get("/").read().decode()
            assert "3 / 3" in html
            srv.post("/qpeek/close")
            time.sleep(0.3)

        assert srv.exit_code == 0

    def test_batch_survey(self, png_files):
        with ServerRunner(port=2038, files=png_files[:2], ask="Rate",
                          choices=["Good", "Bad"], batch=True, group=1,
                          custom_html=None, timeout=10) as srv:
            srv.post("/qpeek/submit", {"choice": "Good"})
            time.sleep(0.3)
            srv.post("/qpeek/submit", {"choice": "Bad"})
            time.sleep(0.3)

        assert srv.exit_code == 0
        results = json.loads(srv.stdout.strip())
        assert len(results) == 2
        assert results[0]["choice"] == "Good"
        assert results[1]["choice"] == "Bad"

    def test_batch_group(self, tmp_path):
        files = []
        for name in ("a1.png", "a2.png", "b1.png", "b2.png"):
            path = str(tmp_path / name)
            _make_png(path)
            files.append(path)

        with ServerRunner(port=2039, files=files, ask="Which?",
                          choices=["Left", "Right"], batch=True, group=2,
                          custom_html=None, timeout=10) as srv:
            # Step 1: a1 + a2
            html = srv.get("/").read().decode()
            assert "1 / 2" in html
            assert "a1.png" in html
            assert "a2.png" in html
            srv.post("/qpeek/submit", {"choice": "Left"})
            time.sleep(0.3)

            # Step 2: b1 + b2
            html = srv.get("/").read().decode()
            assert "2 / 2" in html
            srv.post("/qpeek/submit", {"choice": "Right"})
            time.sleep(0.3)

        results = json.loads(srv.stdout.strip())
        assert len(results) == 2
        assert results[0]["files"] == ["a1.png", "a2.png"]
        assert results[0]["choice"] == "Left"
        assert results[1]["files"] == ["b1.png", "b2.png"]
        assert results[1]["choice"] == "Right"


class TestMeta:
    def test_meta_endpoint(self, png_file):
        with ServerRunner(port=2040, files=[png_file], ask="Question?",
                          choices=["A", "B"], batch=False, group=1,
                          custom_html=None, timeout=10) as srv:
            resp = srv.get("/qpeek/meta")
            meta = json.loads(resp.read())
            assert meta["question"] == "Question?"
            assert meta["choices"] == ["A", "B"]
            assert meta["files"] == ["test.png"]

            srv.post("/qpeek/close")
            time.sleep(0.3)


class TestTimeout:
    def test_timeout_exits_with_code_3(self, png_file):
        with ServerRunner(port=2041, files=[png_file], ask=None, choices=None,
                          batch=False, group=1, custom_html=None, timeout=1) as srv:
            # Don't interact, just wait for timeout
            time.sleep(2)

        assert srv.exit_code == 3


class TestFileServing:
    def test_serves_png(self, png_file):
        with ServerRunner(port=2042, files=[png_file], ask=None, choices=None,
                          batch=False, group=1, custom_html=None, timeout=10) as srv:
            resp = srv.get("/files/test.png")
            assert resp.headers["Content-Type"].startswith("image/")
            data = resp.read()
            assert data[:4] == b'\x89PNG'

            srv.post("/qpeek/close")
            time.sleep(0.3)

    def test_404_for_unknown_file(self, png_file):
        with ServerRunner(port=2043, files=[png_file], ask=None, choices=None,
                          batch=False, group=1, custom_html=None, timeout=10) as srv:
            try:
                srv.get("/files/nonexistent.png")
                assert False, "should have raised"
            except Exception:
                pass

            srv.post("/qpeek/close")
            time.sleep(0.3)


class TestCustomHTML:
    def test_serves_custom_html(self, png_file, tmp_path):
        custom = tmp_path / "custom.html"
        custom.write_text("<html><body>CUSTOM PAGE</body></html>")

        with ServerRunner(port=2044, files=[png_file], ask=None, choices=None,
                          batch=False, group=1, custom_html=str(custom),
                          timeout=10) as srv:
            resp = srv.get("/")
            html = resp.read().decode()
            assert "CUSTOM PAGE" in html

            srv.post("/qpeek/close")
            time.sleep(0.3)

        assert srv.exit_code == 0


class TestAbandoned:
    def test_heartbeat_loss_exits_with_code_1(self, png_file):
        """Browser sends heartbeats then stops. Server detects abandonment."""
        with ServerRunner(port=2045, files=[png_file], ask="Question?",
                          choices=["A", "B"], batch=False, group=1,
                          custom_html=None, timeout=30) as srv:
            srv.get("/")
            srv.get("/qpeek/heartbeat")
            time.sleep(0.3)
            srv.get("/qpeek/heartbeat")
            # Stop sending heartbeats; wait for detection (~10s)
            time.sleep(12)

        assert srv.exit_code == 1

    def test_batch_partial_results_on_abandon(self, png_files):
        """Abandon partway through batch; partial results printed."""
        with ServerRunner(port=2046, files=png_files[:2], ask="Rate",
                          choices=["Good", "Bad"], batch=True, group=1,
                          custom_html=None, timeout=30) as srv:
            # Complete first item
            srv.get("/")
            srv.get("/qpeek/heartbeat")
            srv.post("/qpeek/submit", {"choice": "Good"})
            time.sleep(0.3)
            # Load second item, send one heartbeat, then abandon
            srv.get("/")
            srv.get("/qpeek/heartbeat")
            time.sleep(12)

        assert srv.exit_code == 1
        results = json.loads(srv.stdout.strip())
        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0]["choice"] == "Good"
