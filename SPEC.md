# qpeek - Quick Peek File Viewer

## Overview

qpeek is a transient web server that serves local files over HTTP for viewing on a
remote browser. Primary use case: view images, documents, and text files on a Mac
while SSH'd into a headless Linux box (`dev` via Tailscale). The tool starts, serves,
collects an optional response, prints results to stdout, and exits.

Two audiences drive the design:
1. **Agentic coding loops** (the primary caller): invoke qpeek from scripts, parse
   structured output, automate human-in-the-loop evaluation.
2. **Human reviewers** (the primary viewer): clean UI, minimal friction, fast
   response cycle.

## Architecture

- Python 3 single-package CLI (`qpeek/`), installed via pip into a project venv.
- No external dependencies beyond the Python standard library.
- HTTP server binds `0.0.0.0:PORT` (default 2020, override with `--port`).
- Server serves generated HTML plus file assets; shuts down on completion signal
  from the browser (POST to `/qpeek/close`) or Ctrl-C.
- All structured output goes to stdout as JSON. Diagnostic messages go to stderr.

## Supported File Types

Render inline with appropriate HTML treatment:

| Type | Extensions | Rendering |
|------|-----------|-----------|
| Images | `.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp`, `.svg`, `.webp`, `.tiff`, `.tif` | `<img>` tag, constrained max-width/max-height for consistent sizing |
| PDF | `.pdf` | `<iframe>` or `<embed>`, scrollable |
| Markdown | `.md` | Rendered to HTML (built-in converter, no external deps), scrollable container |
| Plain text | `.txt`, `.log`, `.csv`, `.json`, `.yaml`, `.yml`, `.xml`, `.toml`, `.ini`, `.cfg`, `.conf` | `<pre>` block, monospace, scrollable container |
| HTML | `.html`, `.htm` | `<iframe>` serving the file directly |

Any other extension: exit with error message "unsupported file type: .EXT" and exit code 2.

## Modes

### View Mode (default)

Display one or more files. No survey, no response collected.

```
qpeek cat.png
qpeek cat.png dog.png bird.png
```

- Single file: full-width centered display with a **Close** button.
- Multiple files: stacked vertically or in a responsive grid, labeled with filenames.
  **Close** button at the bottom.
- Clicking **Close**: browser sends POST `/qpeek/close`, server shuts down,
  browser closes the window via JavaScript (`window.close()`). If `window.close()`
  fails (browser policy), display "You may close this tab" message.
- Exit code 0. No stdout output.

### Survey Chat Mode (`--ask`)

Display files and ask a freeform question.

```
qpeek --ask "Is this a high-quality cat picture?" cat.png
qpeek --ask "Compare these two. Which is better?" a.png b.png
```

- Question text displayed prominently above the file(s).
- Single-line text input below the files. Pressing Enter submits.
- **Submit** button also available. On click or Enter: POST response to
  `/qpeek/submit`, server prints JSON to stdout, shuts down, browser closes.
- Stdout (single item): `{"file": "cat.png", "response": "yes, great cat pic!"}`
- Stdout (multiple files shown together): `{"files": ["a.png", "b.png"], "response": "image 1 is better"}`
- Exit code 0 on submit. Exit code 1 if browser closed without submitting.

### Survey Button Mode (`--ask` + `--choices`)

Display files and present fixed choices as buttons.

```
qpeek --ask "Rate this image" --choices "Good,Okay,Bad" cat.png
qpeek --ask "Which is better?" --choices "Left,Right,Neither" a.png b.png
```

- Question displayed above files. Choice buttons displayed below files (large,
  easily clickable).
- No text input field.
- Clicking a choice button: POST to `/qpeek/submit`, server prints JSON, shuts down.
- Stdout: `{"file": "cat.png", "choice": "Good"}`
- Stdout (multiple files): `{"files": ["a.png", "b.png"], "choice": "Left"}`
- Exit code 0 on choice. Exit code 1 if abandoned.

### Batch Mode (`--batch`)

Modifier that applies to any of the above modes. Instead of a single set of files,
each positional argument is treated as one item in a sequence. The browser shows
items one at a time with **Next** (or **Done** on the last item) instead of **Close**/**Submit**.

```
qpeek --batch cat.png dog.png bird.png
qpeek --batch --ask "Rate this image" --choices "Good,Okay,Bad" cat.png dog.png bird.png
qpeek --batch --ask "Describe what you see" img1.png img2.png img3.png
```

- Each positional argument is one batch item (one file per step).
- The UI shows one item at a time. Progress indicator: "1 / 3", "2 / 3", etc.
- In view-only batch mode, button is **Next** (last item: **Done**).
- In survey modes, button is **Next** (submits response and advances) or **Done**
  (submits and closes).
- On completion, stdout is a JSON array with one object per item:
  ```json
  [
    {"file": "cat.png", "choice": "Good"},
    {"file": "dog.png", "choice": "Bad"},
    {"file": "bird.png", "choice": "Okay"}
  ]
  ```
- Exit code 0 if all items completed. Exit code 1 if abandoned partway (partial
  results still printed to stdout as a JSON array of what was completed).

#### Batch with Multi-File Items (`--group N`)

For comparing multiple files per step (e.g., A/B testing):

```
qpeek --batch --group 2 --ask "Which is better?" --choices "Left,Right" \
  a1.png a2.png b1.png b2.png c1.png c2.png
```

- `--group N`: each batch step shows N files side by side. Positional args are
  consumed in groups of N. Total files must be divisible by N (error otherwise).
- Output uses `"files"` array instead of `"file"` string.

### Custom HTML Mode (`--html`)

Serve a user-provided HTML file instead of the generated page.

```
qpeek --html custom_review.html cat.png dog.png
```

- qpeek serves the custom HTML at `/` and files at `/files/<filename>`.
- The custom HTML is responsible for its own layout.
- qpeek provides a shutdown hook: the custom page must POST to `/qpeek/close`
  (view mode) or POST JSON to `/qpeek/submit` (survey mode) to trigger shutdown.
- If `--ask` is also provided, the question text is available at `/qpeek/meta`
  as JSON: `{"question": "...", "choices": [...], "files": [...]}`.
- Exit behavior same as the corresponding non-custom mode.

## API Endpoints (internal, browser-to-server)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Serve generated (or custom) HTML page |
| GET | `/files/<name>` | Serve a file by basename |
| GET | `/qpeek/meta` | JSON metadata (question, choices, files list) |
| POST | `/qpeek/close` | Signal shutdown (view mode) |
| POST | `/qpeek/submit` | Submit response body as JSON, signal shutdown |

## HTML/CSS Design

- Clean, minimal, dark-neutral background (#1a1a2e or similar), light text.
- Images: `max-width: 90vw; max-height: 70vh; object-fit: contain` so they are
  large but never overflow the viewport. Consistent sizing regardless of source
  dimensions.
- Markdown: rendered in a scrollable container with constrained width (max 80ch),
  styled with minimal readable defaults (headings, code blocks, lists).
- Text/code files: monospace, scrollable `<pre>` with soft background, max-height
  with scroll.
- PDF: embedded viewer filling available space, scrollable.
- Buttons: large (min 44px touch target), high contrast, clear labels.
- Filename labels below each file in muted text.
- Survey question: large, prominent text above the content area.
- Text input: full-width single-line input, Enter submits.
- Progress indicator (batch mode): top-right, subtle, e.g., "2 / 5".

## CLI Interface

```
qpeek [OPTIONS] FILE [FILE ...]

Options:
  --port PORT        Port to bind (default: 2020)
  --ask QUESTION     Enable survey mode with the given question
  --choices LIST     Comma-separated choices for button mode (requires --ask)
  --batch            Enable batch mode (one item per file argument)
  --group N          Files per batch step (default: 1, requires --batch)
  --html FILE        Serve custom HTML instead of generated page
  --timeout SECONDS  Auto-shutdown after N seconds with no activity (default: 300)
  --help             Show help and exit
```

## Timeout

Default 300-second inactivity timeout. If no HTTP request is received within the
timeout window, the server shuts down and exits with code 3. This prevents orphaned
qpeek processes if the reviewer walks away. Override with `--timeout` (0 to disable).

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Normal completion (user closed or submitted all items) |
| 1 | Abandoned (browser closed without completing, or Ctrl-C) |
| 2 | Usage error (bad arguments, unsupported file type, file not found) |
| 3 | Timeout (no activity within timeout window) |

## Acceptance Criteria

- [x] `qpeek cat.png` starts server on 0.0.0.0:2020, serves page with image, Close button works, server exits with code 0.
- [x] `qpeek cat.png dog.png` displays both images with filenames labeled.
- [x] `qpeek --ask "question" cat.png` shows question, text input (Enter submits), Submit button; prints JSON to stdout on submit.
- [x] `qpeek --ask "question" --choices "A,B,C" cat.png` shows buttons instead of textarea; prints JSON with `"choice"` key.
- [x] `qpeek --batch img1.png img2.png img3.png` shows one image at a time with Next/Done, no stdout output.
- [x] `qpeek --batch --ask "rate" --choices "Good,Bad" img1.png img2.png` collects one choice per image, prints JSON array.
- [x] `qpeek --batch --group 2 --ask "which?" --choices "Left,Right" a.png b.png c.png d.png` groups files in pairs.
- [x] `--html custom.html` serves the provided HTML, shutdown hooks work.
- [x] Supported file types render correctly: images (png/jpg/gif/svg/webp/bmp/tiff), PDF, markdown (rendered), text/log/csv/json/yaml.
- [x] Unsupported file type prints error and exits with code 2.
- [x] Missing file prints error and exits with code 2.
- [x] `--port 8080` binds to the specified port.
- [x] Timeout (default 300s) shuts down server, exit code 3.
- [x] Ctrl-C shuts down server cleanly, exit code 1.
- [ ] Abandoned session (browser closes without submit in survey mode) exits with code 1.
- [ ] Batch mode partial completion prints partial results as JSON array, exits with code 1.
- [x] No external Python dependencies (stdlib only).
- [x] Installs via pip into a venv.
- [x] Binds to 0.0.0.0, reachable from Tailscale peers.

<!-- SPEC_META: {"date":"2026-04-02","title":"qpeek - Quick Peek File Viewer","criteria_total":19,"criteria_met":16} -->
