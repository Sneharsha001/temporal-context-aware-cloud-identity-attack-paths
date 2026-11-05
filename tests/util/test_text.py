"""Tests for text module."""

from __future__ import annotations

import pytest

from arf_rt.util.text import (
    slugify,
    truncate,
    indent_block,
    wrap_text,
    join_with_oxford_comma,
    pluralize,
    snake_to_camel,
    camel_to_snake,
    strip_ansi,
    dedent,
    shorten,
    extract_version,
)


class TestSlugify:
    """Tests for slugify function."""

    def test_basic(self):
        assert slugify("Hello World") == "hello-world"

    def test_with_special_chars(self):
        assert slugify("Hello, World!") == "hello-world"

    def test_custom_separator(self):
        assert slugify("Hello World", separator="_") == "hello_world"

    def test_max_length(self):
        assert slugify("Hello World", max_length=8) == "hello-wo"

    def test_multiple_spaces(self):
        assert slugify("Hello   World") == "hello-world"

    def test_leading_trailing_spaces(self):
        assert slugify("  Hello World  ") == "hello-world"


class TestTruncate:
    """Tests for truncate function."""

    def test_no_truncation_needed(self):
        assert truncate("Hello", 10) == "Hello"

    def test_truncation(self):
        assert truncate("Hello World", 8) == "Hello …"

    def test_custom_ellipsis(self):
        assert truncate("Hello World", 8, "...") == "Hello ..."

    def test_ellipsis_longer_than_max(self):
        assert truncate("Hello", 2) == "…"

    def test_exact_length(self):
        assert truncate("Hello", 5) == "Hello"


class TestIndentBlock:
    """Tests for indent_block function."""

    def test_basic(self):
        text = "line1\nline2"
        result = indent_block(text)
        assert result == "  line1\n  line2"

    def test_custom_prefix(self):
        text = "line1\nline2"
        result = indent_block(text, prefix="-> ")
        assert result == "-> line1\n-> line2"

    def test_first_line_prefix(self):
        text = "line1\nline2"
        result = indent_block(text, first_line_prefix="* ")
        assert result == "* line1\n  line2"

    def test_empty(self):
        assert indent_block("") == ""

    def test_single_line(self):
        assert indent_block("single") == "  single"


class TestWrapText:
    """Tests for wrap_text function."""

    def test_basic(self):
        text = "This is a long text that should be wrapped to a specific width."
        result = wrap_text(text, width=20)
        lines = result.split("\n")
        assert all(len(line) <= 20 for line in lines)

    def test_paragraphs_preserved(self):
        text = "Paragraph one.\n\nParagraph two."
        result = wrap_text(text, width=40)
        assert "Paragraph one." in result
        assert "Paragraph two." in result

    def test_indent(self):
        text = "This is a test."
        result = wrap_text(text, width=40, indent="  ")
        assert result.startswith("  This")


class TestJoinWithOxfordComma:
    """Tests for join_with_oxford_comma function."""

    def test_empty(self):
        assert join_with_oxford_comma([]) == ""

    def test_single(self):
        assert join_with_oxford_comma(["A"]) == "A"

    def test_two(self):
        assert join_with_oxford_comma(["A", "B"]) == "A and B"

    def test_three(self):
        assert join_with_oxford_comma(["A", "B", "C"]) == "A, B, and C"

    def test_many(self):
        assert join_with_oxford_comma(["A", "B", "C", "D", "E"]) == "A, B, C, D, and E"

    def test_custom_conjunction(self):
        assert join_with_oxford_comma(["A", "B", "C"], "or") == "A, B, or C"


class TestPluralize:
    """Tests for pluralize function."""

    def test_singular(self):
        assert pluralize(1, "item") == "1 item"

    def test_plural(self):
        assert pluralize(3, "item") == "3 items"

    def test_zero(self):
        assert pluralize(0, "item") == "0 items"

    def test_custom_plural(self):
        assert pluralize(1, "child", "children") == "1 child"
        assert pluralize(3, "child", "children") == "3 children"


class TestSnakeToCamel:
    """Tests for snake_to_camel function."""

    def test_camel_case(self):
        assert snake_to_camel("hello_world") == "helloWorld"

    def test_pascal_case(self):
        assert snake_to_camel("hello_world", capitalize_first=True) == "HelloWorld"

    def test_single_word(self):
        assert snake_to_camel("hello") == "hello"

    def test_multiple_underscores(self):
        assert snake_to_camel("a_b_c_d") == "aBCD"


class TestCamelToSnake:
    """Tests for camel_to_snake function."""

    def test_camel_case(self):
        assert camel_to_snake("helloWorld") == "hello_world"

    def test_pascal_case(self):
        assert camel_to_snake("HelloWorld") == "hello_world"

    def test_single_word(self):
        assert camel_to_snake("hello") == "hello"

    def test_acronyms(self):
        assert camel_to_snake("parseXMLFile") == "parse_xml_file"
        assert camel_to_snake("XMLParser") == "xml_parser"


class TestStripAnsi:
    """Tests for strip_ansi function."""

    def test_no_ansi(self):
        assert strip_ansi("hello") == "hello"

    def test_with_ansi(self):
        assert strip_ansi("\x1b[31mhello\x1b[0m") == "hello"

    def test_multiple_ansi(self):
        assert strip_ansi("\x1b[1m\x1b[32mbold green\x1b[0m") == "bold green"


class TestDedent:
    """Tests for dedent function."""

    def test_basic(self):
        text = """
            line1
            line2
        """
        result = dedent(text)
        assert result.startswith("line1")
        assert "  line2" not in result

    def test_already_dedented(self):
        text = "line1\nline2"
        result = dedent(text)
        assert result == "line1\nline2"


class TestShorten:
    """Tests for shorten function."""

    def test_no_shortening(self):
        assert shorten("Hello", 20) == "Hello"

    def test_shortening(self):
        result = shorten("Hello world this is a test", 15)
        assert len(result) <= 15
        assert result.endswith("...")

    def test_custom_placeholder(self):
        result = shorten("Hello world", 10, ">>>")
        assert result.endswith(">>>")


class TestExtractVersion:
    """Tests for extract_version function."""

    def test_with_v_prefix(self):
        assert extract_version("Version v1.2.3 released") == "1.2.3"

    def test_without_v_prefix(self):
        assert extract_version("Release 2.0.0") == "2.0.0"

    def test_with_prerelease(self):
        assert extract_version("v1.0.0-alpha.1") == "1.0.0-alpha.1"

    def test_with_build(self):
        assert extract_version("v1.0.0+build.123") == "1.0.0+build.123"

    def test_no_version(self):
        assert extract_version("No version here") is None