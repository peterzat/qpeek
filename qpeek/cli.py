"""CLI argument parsing and entry point."""
import argparse
import os
import sys


SUPPORTED_EXTENSIONS = {
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp", ".tiff", ".tif",
    # PDF
    ".pdf",
    # Markdown
    ".md",
    # Plain text
    ".txt", ".log", ".csv", ".json", ".yaml", ".yml", ".xml", ".toml", ".ini",
    ".cfg", ".conf",
    # HTML
    ".html", ".htm",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp", ".tiff", ".tif"}
PDF_EXTENSIONS = {".pdf"}
MARKDOWN_EXTENSIONS = {".md"}
TEXT_EXTENSIONS = {".txt", ".log", ".csv", ".json", ".yaml", ".yml", ".xml", ".toml", ".ini", ".cfg", ".conf"}
HTML_EXTENSIONS = {".html", ".htm"}


def file_type(path):
    """Return the category of a file based on extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in PDF_EXTENSIONS:
        return "pdf"
    if ext in MARKDOWN_EXTENSIONS:
        return "markdown"
    if ext in TEXT_EXTENSIONS:
        return "text"
    if ext in HTML_EXTENSIONS:
        return "html"
    return None


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="qpeek",
        description="Quick Peek - transient file viewer over HTTP",
    )
    parser.add_argument("files", nargs="+", metavar="FILE", help="File(s) to serve")
    parser.add_argument("--port", type=int, default=2020, help="Port to bind (default: 2020)")
    parser.add_argument("--ask", metavar="QUESTION", help="Survey question to display")
    parser.add_argument("--choices", metavar="LIST", help="Comma-separated choices (requires --ask)")
    parser.add_argument("--batch", action="store_true", help="Batch mode: one item per file argument")
    parser.add_argument("--group", type=int, default=1, metavar="N", help="Files per batch step (requires --batch)")
    parser.add_argument("--html", metavar="FILE", help="Serve custom HTML instead of generated page")
    parser.add_argument("--timeout", type=int, default=300, metavar="SECONDS",
                        help="Inactivity timeout in seconds (default: 300, 0 to disable)")
    return parser.parse_args(argv)


def validate_args(args):
    """Validate arguments, return error message or None."""
    if args.choices and not args.ask:
        return "--choices requires --ask"
    if args.group != 1 and not args.batch:
        return "--group requires --batch"
    if args.batch and args.group > 1:
        if len(args.files) % args.group != 0:
            return f"number of files ({len(args.files)}) not divisible by --group {args.group}"

    # Validate files exist and have supported types
    all_files = list(args.files)
    if args.html:
        if not os.path.isfile(args.html):
            return f"custom HTML file not found: {args.html}"

    for f in all_files:
        if not os.path.isfile(f):
            return f"file not found: {f}"
        ext = os.path.splitext(f)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return f"unsupported file type: {ext}"

    return None


def main(argv=None):
    args = parse_args(argv)
    error = validate_args(args)
    if error:
        print(f"qpeek: {error}", file=sys.stderr)
        sys.exit(2)

    # Parse choices into a list
    choices = None
    if args.choices:
        choices = [c.strip() for c in args.choices.split(",") if c.strip()]

    # Resolve file paths to absolute
    args.files = [os.path.abspath(f) for f in args.files]
    if args.html:
        args.html = os.path.abspath(args.html)

    from qpeek.server import run_server
    exit_code = run_server(
        files=args.files,
        port=args.port,
        ask=args.ask,
        choices=choices,
        batch=args.batch,
        group=args.group,
        custom_html=args.html,
        timeout=args.timeout,
    )
    sys.exit(exit_code)
