"""Minimal markdown to HTML converter using only stdlib.

Supports: headings, code blocks (fenced), inline code, bold, italic, links,
unordered/ordered lists, horizontal rules, paragraphs, and line breaks.
"""
import html
import re


def render_markdown(text):
    """Convert markdown text to HTML string."""
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # Fenced code block
        if line.startswith("```"):
            lang = line[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            code = html.escape("\n".join(code_lines))
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            out.append(f"<pre><code{cls}>{code}</code></pre>")
            continue

        # Horizontal rule
        stripped = line.strip()
        if re.match(r"^[-*_]{3,}\s*$", stripped) and len(stripped) >= 3:
            out.append("<hr>")
            i += 1
            continue

        # Heading
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            level = len(m.group(1))
            content = _inline(m.group(2))
            out.append(f"<h{level}>{content}</h{level}>")
            i += 1
            continue

        # Unordered list
        if re.match(r"^[\s]*[-*+]\s+", line):
            items, i = _collect_list(lines, i, r"^[\s]*[-*+]\s+(.*)")
            out.append("<ul>" + "".join(f"<li>{_inline(it)}</li>" for it in items) + "</ul>")
            continue

        # Ordered list
        if re.match(r"^[\s]*\d+\.\s+", line):
            items, i = _collect_list(lines, i, r"^[\s]*\d+\.\s+(.*)")
            out.append("<ol>" + "".join(f"<li>{_inline(it)}</li>" for it in items) + "</ol>")
            continue

        # Blank line
        if not stripped:
            i += 1
            continue

        # Paragraph: collect consecutive non-blank, non-special lines
        para_lines = []
        while i < len(lines) and lines[i].strip() and not _is_block_start(lines[i]):
            para_lines.append(lines[i])
            i += 1
        out.append(f"<p>{_inline('<br>'.join(para_lines))}</p>")

    return "\n".join(out)


def _is_block_start(line):
    """Check if a line starts a block-level element."""
    if line.startswith("```"):
        return True
    if re.match(r"^#{1,6}\s+", line):
        return True
    if re.match(r"^[-*_]{3,}\s*$", line.strip()):
        return True
    if re.match(r"^[\s]*[-*+]\s+", line):
        return True
    if re.match(r"^[\s]*\d+\.\s+", line):
        return True
    return False


def _collect_list(lines, i, pattern):
    """Collect consecutive list items matching pattern."""
    items = []
    while i < len(lines):
        m = re.match(pattern, lines[i])
        if m:
            items.append(m.group(1))
            i += 1
        else:
            break
    return items, i


def _inline(text):
    """Process inline markdown elements."""
    # Escape HTML first, then apply markdown
    # But we need to handle the case where text already contains <br> tags
    br_placeholder = "\x00BR\x00"
    text = text.replace("<br>", br_placeholder)
    text = html.escape(text)
    text = text.replace(br_placeholder, "<br>")

    # Inline code (must come before bold/italic to avoid conflicts)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text)
    # Italic
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"_(.+?)_", r"<em>\1</em>", text)
    # Links
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)

    return text
