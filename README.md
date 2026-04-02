# qpeek

A transient web server for viewing files on a headless Linux box from a remote browser. Start it, open the URL, interact, done. When you close or submit, the server exits.

qpeek is designed for two audiences: **agentic coding loops** that need human-in-the-loop evaluation, and **human reviewers** who want zero-friction file viewing over a network.

## Installation

Requires Python 3.10+. No external dependencies.

```bash
cd qpeek
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

## Quick start

```bash
# View an image
qpeek photo.png

# View multiple files
qpeek output1.png output2.png result.csv

# Ask a question with freeform text response
qpeek --ask "Is this output correct?" result.png

# Ask with button choices
qpeek --ask "Rate this image" --choices "Good,Okay,Bad" photo.png

# Batch mode: rate a series of images one at a time
qpeek --batch --ask "Rate this" --choices "Good,Bad" img1.png img2.png img3.png

# A/B comparison: show pairs side by side
qpeek --batch --group 2 --ask "Which is better?" --choices "Left,Right" \
  original1.png enhanced1.png original2.png enhanced2.png

# Serve a custom HTML page
qpeek --html my_review.html data1.png data2.png
```

The server binds to `0.0.0.0` on port 2020 by default. On startup it prints the URL with the machine's IP address for easy copy/paste:

```
  qpeek ready:  http://100.70.19.124:2020
```

## Modes

### View mode (default)

Displays one or more files with a **Close** button. No output to stdout.

### Survey chat (`--ask`)

Displays files with a question and a text input field. Pressing Enter or clicking Submit sends the response. Prints JSON to stdout:

```json
{"file": "photo.png", "response": "looks good to me"}
```

### Survey buttons (`--ask` + `--choices`)

Displays files with a question and clickable choice buttons. No text input. Prints JSON to stdout:

```json
{"file": "photo.png", "choice": "Good"}
```

### Batch mode (`--batch`)

Applies to any of the above. Shows one item at a time with a progress indicator and Next/Done buttons. Collects results into a JSON array on stdout:

```json
[
  {"file": "img1.png", "choice": "Good"},
  {"file": "img2.png", "choice": "Bad"},
  {"file": "img3.png", "choice": "Good"}
]
```

Use `--group N` to show N files per step (for A/B or multi-way comparisons). Files are consumed in groups; the total must be divisible by N.

### Custom HTML (`--html`)

Serves a user-provided HTML file instead of the generated page. qpeek handles the serve/shutdown lifecycle; the custom page handles layout. Files are available at `/files/<filename>`, metadata at `/qpeek/meta`. The page must POST to `/qpeek/close` or `/qpeek/submit` to trigger shutdown.

## Supported file types

| Type | Extensions | Rendering |
|------|-----------|-----------|
| Images | png, jpg, jpeg, gif, bmp, svg, webp, tiff, tif | Inline with consistent sizing |
| PDF | pdf | Embedded viewer, scrollable |
| Markdown | md | Rendered to HTML in a scrollable container |
| Plain text | txt, log, csv, json, yaml, yml, xml, toml, ini, cfg, conf | Monospace `<pre>` block |
| HTML | html, htm | Embedded iframe |

Unsupported extensions produce an error (exit code 2).

## CLI reference

```
qpeek [OPTIONS] FILE [FILE ...]

Options:
  --port PORT        Port to bind (default: 2020)
  --ask QUESTION     Enable survey mode with the given question
  --choices LIST     Comma-separated choices for button mode (requires --ask)
  --batch            Enable batch mode (one item per file argument)
  --group N          Files per batch step (default: 1, requires --batch)
  --html FILE        Serve custom HTML instead of generated page
  --timeout SECONDS  Inactivity timeout (default: 300, 0 to disable)
  --help             Show help and exit
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Normal completion |
| 1 | Abandoned (browser closed without completing, or Ctrl-C) |
| 2 | Usage error (bad arguments, unsupported file type, missing file) |
| 3 | Timeout (no activity within timeout window) |

## Use in agentic coding loops

qpeek exists primarily to support human-in-the-loop evaluation within automated coding workflows. When an AI coding agent generates visual output (images, charts, rendered documents) or needs subjective human judgment, it needs a way to show artifacts to a human reviewer and collect structured feedback, all without breaking the automation flow.

### The problem

Agentic coding loops running on a headless server have no display. The agent can generate files but cannot show them to a human. Common workarounds (scp, rsync, shared drives) add friction and break the feedback loop. The human needs to see the output, make a judgment, and return that judgment to the agent as quickly as possible.

### How qpeek fits in

qpeek is a blocking call. The agent invokes it, qpeek prints a URL to stderr (visible in the agent's terminal output), and then blocks until the human responds. The human opens the URL, reviews the content, submits their response, and qpeek exits with structured JSON on stdout that the agent can parse.

This makes the integration pattern simple:

```bash
# Agent generates an image, asks the human to evaluate it
result=$(qpeek --ask "Does this look correct?" --choices "Yes,No" output.png)
# result is: {"file": "output.png", "choice": "Yes"}
```

```bash
# Agent wants human to pick the best of several generated variants
result=$(qpeek --batch --group 2 --ask "Which is better?" --choices "Left,Right,Same" \
  variant_a.png variant_b.png variant_c.png variant_d.png)
# result is a JSON array with one choice per pair
```

```bash
# Agent wants freeform feedback
result=$(qpeek --ask "What should I change about this layout?" mockup.png)
# result is: {"file": "mockup.png", "response": "make the header smaller"}
```

### Exit code as signal

The agent can use the exit code to detect whether the human actually engaged:

```bash
qpeek --ask "Review this" output.png
status=$?
if [ $status -eq 0 ]; then
    # human submitted a response
elif [ $status -eq 1 ]; then
    # human closed the browser without responding
elif [ $status -eq 3 ]; then
    # timed out waiting for human
fi
```

### Batch evaluation

For workflows that generate many artifacts (training runs, style transfer experiments, generated assets), batch mode collects all ratings in one session:

```bash
result=$(qpeek --batch --ask "Quality?" --choices "Keep,Discard" \
  generated_001.png generated_002.png generated_003.png)
# result: [{"file": "generated_001.png", "choice": "Keep"}, ...]
```

The agent receives the full array when the human finishes, then can filter, retry, or proceed based on the ratings.

### Custom flows

When the built-in modes are not sufficient, the agent can generate a custom HTML page tailored to the specific evaluation task and use qpeek purely for the serve/collect/shutdown lifecycle:

```bash
# Agent writes a custom comparison page
cat > /tmp/review.html << 'EOF'
<html>
<!-- custom layout, side-by-side diffs, annotated images, etc. -->
<script>
// POST to /qpeek/submit with structured JSON when done
</script>
</html>
EOF

result=$(qpeek --ask "Review" --html /tmp/review.html output1.png output2.png)
```

Metadata about the current session (question, choices, file list) is available at `/qpeek/meta` for custom pages that want to stay generic.

### Invocation from agent tooling

qpeek blocks until the browser session ends. Agent frameworks that capture subprocess output in buffered or background mode will not see the URL until the process exits, which may be never.

Launch qpeek in a shell background and read the URL from the first line of stderr:

```bash
qpeek photo.png &
# stderr prints:  qpeek ready:  http://100.70.19.124:2020
```

## Networking

qpeek binds to `0.0.0.0` so it is reachable from any network interface. It is designed for use over a Tailscale mesh or similar private network where the headless server and the reviewer's browser are on the same trusted network. There is no authentication or encryption; do not expose qpeek to untrusted networks.

The default inactivity timeout (300 seconds) prevents orphaned servers if the reviewer disconnects.
