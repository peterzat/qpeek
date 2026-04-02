"""Tests for the markdown renderer."""
from qpeek.markdown import render_markdown


class TestHeadings:
    def test_h1(self):
        assert "<h1>Title</h1>" in render_markdown("# Title")

    def test_h2(self):
        assert "<h2>Sub</h2>" in render_markdown("## Sub")

    def test_h3(self):
        assert "<h3>Deep</h3>" in render_markdown("### Deep")


class TestInline:
    def test_bold(self):
        result = render_markdown("**bold**")
        assert "<strong>bold</strong>" in result

    def test_italic(self):
        result = render_markdown("*italic*")
        assert "<em>italic</em>" in result

    def test_code(self):
        result = render_markdown("`code`")
        assert "<code>code</code>" in result

    def test_link(self):
        result = render_markdown("[text](http://example.com)")
        assert '<a href="http://example.com">text</a>' in result

    def test_escaping(self):
        result = render_markdown("a < b & c")
        assert "&lt;" in result
        assert "&amp;" in result


class TestCodeBlocks:
    def test_fenced(self):
        md = "```python\ndef foo():\n    pass\n```"
        result = render_markdown(md)
        assert "<pre><code" in result
        assert "def foo():" in result
        assert "language-python" in result

    def test_fenced_no_lang(self):
        md = "```\nhello\n```"
        result = render_markdown(md)
        assert "<pre><code>" in result

    def test_html_escaped_in_code(self):
        md = "```\n<div>test</div>\n```"
        result = render_markdown(md)
        assert "&lt;div&gt;" in result


class TestLists:
    def test_unordered(self):
        md = "- one\n- two\n- three"
        result = render_markdown(md)
        assert "<ul>" in result
        assert "<li>one</li>" in result
        assert result.count("<li>") == 3

    def test_ordered(self):
        md = "1. first\n2. second"
        result = render_markdown(md)
        assert "<ol>" in result
        assert "<li>first</li>" in result

    def test_asterisk_list(self):
        md = "* item"
        result = render_markdown(md)
        assert "<ul>" in result
        assert "<li>item</li>" in result


class TestParagraphs:
    def test_simple(self):
        result = render_markdown("Hello world.")
        assert "<p>Hello world.</p>" in result

    def test_multi_line(self):
        result = render_markdown("Line one\nLine two")
        assert "<p>" in result
        assert "Line one" in result
        assert "Line two" in result


class TestHorizontalRule:
    def test_dashes(self):
        result = render_markdown("---")
        assert "<hr>" in result

    def test_asterisks(self):
        result = render_markdown("***")
        assert "<hr>" in result
