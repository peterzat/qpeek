# qpeek

Transient web server for viewing files from a headless Linux box. Stdlib-only Python, no external dependencies.

## Build and test

```bash
. .venv/bin/activate
python -m pytest tests/
```

To reinstall after changes to pyproject.toml:

```bash
pip install -e .
```

## Running

```bash
. .venv/bin/activate
qpeek [OPTIONS] FILE|DIR [FILE ...]
```

Or without activating: `.venv/bin/qpeek`

## Project layout

- `qpeek/cli.py` -- argument parsing, file type detection, validation
- `qpeek/server.py` -- HTTP server, request routing, shutdown lifecycle, serve mode (static file server)
- `qpeek/html_gen.py` -- HTML/CSS/JS page generation for all modes
- `qpeek/markdown.py` -- stdlib-only markdown to HTML renderer
- `tests/` -- unit tests (cli, markdown) and integration tests (server)

## Design notes

- Server binds `0.0.0.0` for Tailscale access. URL printed with Tailscale IP (via `tailscale ip -4`) so Safari does not upgrade to HTTPS.
- `ThreadingHTTPServer` for concurrent request handling.
- All structured output goes to stdout as JSON. Diagnostics go to stderr.
- See SPEC.md for full design and acceptance criteria.
