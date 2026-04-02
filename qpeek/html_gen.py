"""HTML page generation for all qpeek modes."""
import html
import os

from qpeek.cli import file_type
from qpeek.markdown import render_markdown


CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    background: #1a1a2e; color: #e0e0e0; font-family: -apple-system, BlinkMacSystemFont,
    "Segoe UI", Roboto, Helvetica, Arial, sans-serif; min-height: 100vh;
    display: flex; flex-direction: column; align-items: center; padding: 24px;
}
.progress { position: fixed; top: 16px; right: 24px; font-size: 14px; color: #888; }
.question { font-size: 22px; font-weight: 600; margin-bottom: 20px; text-align: center;
    max-width: 800px; line-height: 1.4; }
.files { display: flex; flex-wrap: wrap; justify-content: center; gap: 20px;
    margin-bottom: 24px; width: 100%; max-width: 1200px; }
.file-item { display: flex; flex-direction: column; align-items: center; }
.file-label { font-size: 13px; color: #888; margin-top: 6px; word-break: break-all;
    max-width: 90vw; text-align: center; }
.file-item img { max-width: 90vw; max-height: 70vh; object-fit: contain; border-radius: 4px; }
.file-item iframe { width: 90vw; max-width: 900px; height: 70vh; border: 1px solid #333;
    border-radius: 4px; background: #fff; }
.file-item .text-container { background: #16213e; border: 1px solid #333; border-radius: 4px;
    padding: 16px; max-width: 90vw; width: 900px; max-height: 70vh; overflow: auto; }
.file-item .text-container pre { font-family: "SF Mono", "Fira Code", "Cascadia Code",
    monospace; font-size: 14px; line-height: 1.5; white-space: pre-wrap;
    word-wrap: break-word; color: #e0e0e0; }
.file-item .md-container { background: #16213e; border: 1px solid #333; border-radius: 4px;
    padding: 24px; max-width: 80ch; width: 100%; max-height: 70vh; overflow: auto;
    line-height: 1.6; }
.md-container h1, .md-container h2, .md-container h3, .md-container h4 {
    margin: 16px 0 8px; color: #f0f0f0; }
.md-container h1 { font-size: 24px; border-bottom: 1px solid #333; padding-bottom: 8px; }
.md-container h2 { font-size: 20px; }
.md-container h3 { font-size: 17px; }
.md-container p { margin: 8px 0; }
.md-container code { background: #0f3460; padding: 2px 6px; border-radius: 3px;
    font-family: monospace; font-size: 13px; }
.md-container pre { background: #0f3460; padding: 12px; border-radius: 4px;
    overflow-x: auto; margin: 8px 0; }
.md-container pre code { background: none; padding: 0; }
.md-container ul, .md-container ol { margin: 8px 0 8px 24px; }
.md-container li { margin: 4px 0; }
.md-container a { color: #7ec8e3; }
.md-container hr { border: none; border-top: 1px solid #333; margin: 16px 0; }
input[type="text"] { width: 100%; max-width: 800px; padding: 12px;
    font-size: 16px; border: 1px solid #444; border-radius: 4px; background: #16213e;
    color: #e0e0e0; margin-bottom: 16px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
input[type="text"]:focus { outline: none; border-color: #7ec8e3; }
.actions { display: flex; gap: 12px; flex-wrap: wrap; justify-content: center; }
button { min-width: 120px; min-height: 44px; padding: 10px 24px; font-size: 16px;
    font-weight: 600; border: none; border-radius: 6px; cursor: pointer;
    transition: background 0.15s; }
button.primary { background: #e94560; color: #fff; }
button.primary:hover { background: #c73e54; }
button.choice { background: #533483; color: #fff; }
button.choice:hover { background: #6b44a0; }
button.close { background: #444; color: #e0e0e0; }
button.close:hover { background: #555; }
.done-msg { font-size: 18px; color: #888; margin-top: 40px; }
"""


def _file_html(basename):
    """Generate HTML to display a single file based on its type."""
    ft = file_type(basename)
    src = f"/files/{html.escape(basename)}"
    label = f'<div class="file-label">{html.escape(basename)}</div>'

    if ft == "image":
        return f'<div class="file-item"><img src="{src}" alt="{html.escape(basename)}">{label}</div>'
    if ft == "pdf":
        return f'<div class="file-item"><iframe src="{src}"></iframe>{label}</div>'
    if ft == "html":
        return f'<div class="file-item"><iframe src="{src}"></iframe>{label}</div>'
    # markdown and text are rendered server-side and embedded
    # Use a placeholder that will be replaced with actual content
    return f'<div class="file-item"><div class="content-placeholder" data-file="{html.escape(basename)}"></div>{label}</div>'


def generate_page(files, ask=None, choices=None, batch=False, group=1,
                  batch_index=0, batch_total=1, file_contents=None):
    """Generate the full HTML page.

    Args:
        files: list of absolute file paths for the current view
        ask: survey question or None
        choices: list of choice strings or None
        batch: whether in batch mode
        group: files per batch step
        batch_index: current batch step (0-based)
        batch_total: total batch steps
        file_contents: dict mapping basename to pre-rendered HTML content
                       (for markdown and text files)
    """
    file_contents = file_contents or {}
    basenames = [os.path.basename(f) for f in files]
    is_last = (batch_index >= batch_total - 1)
    is_survey = ask is not None

    parts = [f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>qpeek</title>
<style>{CSS}</style>
</head>
<body>"""]

    # Progress indicator
    if batch and batch_total > 1:
        parts.append(f'<div class="progress">{batch_index + 1} / {batch_total}</div>')

    # Question
    if ask:
        parts.append(f'<div class="question">{html.escape(ask)}</div>')

    # Files
    parts.append('<div class="files">')
    for bn in basenames:
        ft = file_type(bn)
        if ft in ("markdown", "text") and bn in file_contents:
            cls = "md-container" if ft == "markdown" else "text-container"
            label = f'<div class="file-label">{html.escape(bn)}</div>'
            if ft == "text":
                parts.append(f'<div class="file-item"><div class="{cls}"><pre>{file_contents[bn]}</pre></div>{label}</div>')
            else:
                parts.append(f'<div class="file-item"><div class="{cls}">{file_contents[bn]}</div>{label}</div>')
        else:
            parts.append(_file_html(bn))
    parts.append("</div>")

    # Input area
    if is_survey and choices:
        parts.append('<div class="actions">')
        for c in choices:
            parts.append(f'<button class="choice" onclick="submitChoice(\'{html.escape(c, quote=True)}\')">'
                         f'{html.escape(c)}</button>')
        parts.append("</div>")
    elif is_survey:
        parts.append('<input type="text" id="response" placeholder="Type your response..." autofocus>')

    # Action buttons
    parts.append('<div class="actions" style="margin-top: 12px;">')
    if is_survey and not choices:
        if batch and not is_last:
            parts.append('<button class="primary" onclick="submitText(\'next\')">Next</button>')
        elif batch:
            parts.append('<button class="primary" onclick="submitText(\'done\')">Done</button>')
        else:
            parts.append('<button class="primary" onclick="submitText(\'done\')">Submit</button>')
    elif not is_survey:
        if batch and not is_last:
            parts.append('<button class="primary" onclick="doClose(\'next\')">Next</button>')
        elif batch:
            parts.append('<button class="primary" onclick="doClose(\'done\')">Done</button>')
        else:
            parts.append('<button class="close" onclick="doClose(\'done\')">Close</button>')
    parts.append("</div>")

    # Done message (hidden, shown after close)
    parts.append('<div class="done-msg" id="done-msg" style="display:none;">You may close this tab.</div>')

    # JavaScript
    parts.append(f"""
<script>
function submitChoice(choice) {{
    fetch('/qpeek/submit', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{choice: choice}})
    }}).then(function() {{
        {'location.reload();' if batch and not is_last else 'tryClose();'}
    }});
}}

function submitText(action) {{
    var text = document.getElementById('response').value;
    fetch('/qpeek/submit', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{response: text}})
    }}).then(function() {{
        {'location.reload();' if batch and not is_last else 'tryClose();'}
    }});
}}

function doClose(action) {{
    fetch('/qpeek/close', {{method: 'POST'}}).then(function() {{
        {'location.reload();' if batch and not is_last else 'tryClose();'}
    }});
}}

function tryClose() {{
    window.close();
    setTimeout(function() {{
        document.getElementById('done-msg').style.display = 'block';
        document.querySelector('.files').style.display = 'none';
        document.querySelector('.question') && (document.querySelector('.question').style.display = 'none');
        var inp = document.querySelector('input[type="text"]');
        if (inp) inp.style.display = 'none';
        var acts = document.querySelectorAll('.actions');
        acts.forEach(function(a) {{ a.style.display = 'none'; }});
    }}, 300);
}}

var inp = document.getElementById('response');
if (inp) {{
    inp.addEventListener('keydown', function(e) {{
        if (e.key === 'Enter') {{
            e.preventDefault();
            document.querySelector('.primary').click();
        }}
    }});
}}
</script>
</body>
</html>""")

    return "\n".join(parts)
