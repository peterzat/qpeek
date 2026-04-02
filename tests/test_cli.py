"""Tests for CLI argument parsing and validation."""
import os
import tempfile
import pytest

from qpeek.cli import parse_args, validate_args, file_type, SUPPORTED_EXTENSIONS


class TestFileType:
    def test_image_types(self):
        for ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp", ".tiff", ".tif"):
            assert file_type(f"test{ext}") == "image"

    def test_pdf(self):
        assert file_type("doc.pdf") == "pdf"

    def test_markdown(self):
        assert file_type("readme.md") == "markdown"

    def test_text_types(self):
        for ext in (".txt", ".log", ".csv", ".json", ".yaml", ".yml", ".xml", ".toml", ".ini", ".cfg", ".conf"):
            assert file_type(f"test{ext}") == "text"

    def test_html_types(self):
        assert file_type("page.html") == "html"
        assert file_type("page.htm") == "html"

    def test_unsupported(self):
        assert file_type("test.xyz") is None
        assert file_type("test.mp4") is None

    def test_case_insensitive(self):
        assert file_type("TEST.PNG") == "image"
        assert file_type("DOC.PDF") == "pdf"


class TestParseArgs:
    def test_single_file(self):
        args = parse_args(["test.png"])
        assert args.files == ["test.png"]
        assert args.port == 2020
        assert args.ask is None
        assert args.choices is None
        assert not args.batch
        assert args.group == 1
        assert args.html is None
        assert args.timeout == 300

    def test_multiple_files(self):
        args = parse_args(["a.png", "b.jpg", "c.gif"])
        assert args.files == ["a.png", "b.jpg", "c.gif"]

    def test_ask(self):
        args = parse_args(["--ask", "Rate this", "test.png"])
        assert args.ask == "Rate this"

    def test_choices(self):
        args = parse_args(["--ask", "q", "--choices", "A,B,C", "test.png"])
        assert args.choices == "A,B,C"

    def test_batch(self):
        args = parse_args(["--batch", "a.png", "b.png"])
        assert args.batch is True

    def test_group(self):
        args = parse_args(["--batch", "--group", "2", "a.png", "b.png"])
        assert args.group == 2

    def test_port(self):
        args = parse_args(["--port", "8080", "test.png"])
        assert args.port == 8080

    def test_timeout(self):
        args = parse_args(["--timeout", "0", "test.png"])
        assert args.timeout == 0

    def test_html(self):
        args = parse_args(["--html", "custom.html", "test.png"])
        assert args.html == "custom.html"


class TestValidateArgs:
    def _make_file(self, suffix=".png"):
        f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        f.close()
        return f.name

    def test_valid_single_file(self):
        path = self._make_file()
        try:
            args = parse_args([path])
            assert validate_args(args) is None
        finally:
            os.unlink(path)

    def test_missing_file(self):
        args = parse_args(["/nonexistent/file.png"])
        err = validate_args(args)
        assert "file not found" in err

    def test_unsupported_extension(self):
        path = self._make_file(suffix=".xyz")
        try:
            args = parse_args([path])
            err = validate_args(args)
            assert "unsupported file type" in err
        finally:
            os.unlink(path)

    def test_choices_without_ask(self):
        path = self._make_file()
        try:
            args = parse_args(["--choices", "A,B", path])
            err = validate_args(args)
            assert "--choices requires --ask" in err
        finally:
            os.unlink(path)

    def test_group_without_batch(self):
        path = self._make_file()
        try:
            args = parse_args(["--group", "2", path])
            err = validate_args(args)
            assert "--group requires --batch" in err
        finally:
            os.unlink(path)

    def test_group_not_divisible(self):
        paths = [self._make_file() for _ in range(3)]
        try:
            args = parse_args(["--batch", "--group", "2"] + paths)
            err = validate_args(args)
            assert "not divisible" in err
        finally:
            for p in paths:
                os.unlink(p)

    def test_group_divisible(self):
        paths = [self._make_file() for _ in range(4)]
        try:
            args = parse_args(["--batch", "--group", "2"] + paths)
            assert validate_args(args) is None
        finally:
            for p in paths:
                os.unlink(p)
