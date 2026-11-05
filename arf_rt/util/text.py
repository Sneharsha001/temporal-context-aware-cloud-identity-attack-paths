"""
arf_rt/util/text.py - Text processing utilities for ARF-RT.

Provides helpers for string normalization, formatting, and manipulation
that are shared across pipeline stages.
"""

from __future__ import annotations

import re
import textwrap
from typing import Sequence


def slugify(text: str, separator: str = "-", max_length: int | None = None) -> str:
    """Convert *text* to a URL/filename-safe slug.

    Args:
        text: Input string.
        separator: Character used to join words (default ``"-"``).
        max_length: If given, truncate the slug to at most this many characters.

    Returns:
        A lowercase, ASCII-safe slug string.

    Examples:
        >>> slugify("Hello World!")
        'hello-world'
        >>> slugify("ARF-RT: Temporal Context", separator="_")
        'arf-rt-temporal-context'
    """
    # Normalise whitespace and lower-case
    text = text.strip().lower()
    # Replace non-alphanumeric characters (except hyphens) with separator
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", separator, text)
    text = text.strip(separator)

    if max_length is not None:
        text = text[:max_length].rstrip(separator)

    return text


def truncate(text: str, max_chars: int, ellipsis: str = "…") -> str:
    """Truncate *text* to *max_chars*, appending *ellipsis* if cut.

    Args:
        text: The string to truncate.
        max_chars: Maximum character count of the returned string,
            including *ellipsis*.
        ellipsis: Appended when truncation occurs (default ``"…"``).

    Returns:
        Truncated string.

    Examples:
        >>> truncate("Hello, World!", 8)
        'Hello, …'
        >>> truncate("Short", 100)
        'Short'
    """
    if len(text) <= max_chars:
        return text
    cut = max_chars - len(ellipsis)
    if cut <= 0:
        return ellipsis[:max_chars]
    return text[:cut] + ellipsis


def indent_block(text: str, prefix: str = "  ", first_line_prefix: str | None = None) -> str:
    """Indent each line of *text* with *prefix*.

    Args:
        text: Multi-line input string.
        prefix: String prepended to every line (default: two spaces).
        first_line_prefix: If given, used only for the first line;
            subsequent lines use *prefix*.

    Returns:
        Indented string.
    """
    lines = text.splitlines(keepends=True)
    if not lines:
        return text

    result = []
    for i, line in enumerate(lines):
        p = (first_line_prefix if i == 0 and first_line_prefix is not None else prefix)
        result.append(p + line)
    return "".join(result)


def wrap_text(text: str, width: int = 80, indent: str = "") -> str:
    """Wrap *text* to *width* characters, preserving paragraph breaks.

    Args:
        text: Input string.
        width: Maximum line width.
        indent: Prefix applied to each wrapped line.

    Returns:
        Wrapped string.
    """
    paragraphs = re.split(r"\n{2,}", text.strip())
    wrapped = []
    for para in paragraphs:
        filled = textwrap.fill(
            para.strip(), width=width, subsequent_indent=indent
        )
        wrapped.append(filled)
    return "\n\n".join(wrapped)


def join_with_oxford_comma(items: Sequence[str], conjunction: str = "and") -> str:
    """Join a sequence of strings with an Oxford comma.

    Args:
        items: Sequence of strings.
        conjunction: Final joining word (default ``"and"``).

    Returns:
        Formatted string.

    Examples:
        >>> join_with_oxford_comma(["A", "B", "C"])
        'A, B, and C'
        >>> join_with_oxford_comma(["X", "Y"])
        'X and Y'
    """
    items = list(items)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} {conjunction} {items[1]}"
    return ", ".join(items[:-1]) + f", {conjunction} {items[-1]}"


def pluralize(count: int, singular: str, plural: str | None = None) -> str:
    """Return singular or plural form based on count.

    Args:
        count: Number of items.
        singular: Singular form.
        plural: Plural form (defaults to singular + 's').

    Returns:
        Appropriate form for the count.

    Examples:
        >>> pluralize(1, "item")
        '1 item'
        >>> pluralize(3, "item")
        '3 items'
        >>> pluralize(0, "child", "children")
        '0 children'
    """
    if plural is None:
        plural = singular + "s"
    return f"{count} {singular if count == 1 else plural}"


def snake_to_camel(snake_str: str, capitalize_first: bool = False) -> str:
    """Convert snake_case to camelCase or PascalCase.

    Args:
        snake_str: Input string in snake_case.
        capitalize_first: If True, return PascalCase (default: camelCase).

    Returns:
        Converted string.

    Examples:
        >>> snake_to_camel("hello_world")
        'helloWorld'
        >>> snake_to_camel("hello_world", capitalize_first=True)
        'HelloWorld'
    """
    parts = snake_str.split("_")
    if capitalize_first:
        return "".join(p.capitalize() for p in parts)
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def camel_to_snake(camel_str: str) -> str:
    """Convert camelCase or PascalCase to snake_case.

    Args:
        camel_str: Input string in camelCase or PascalCase.

    Returns:
        Converted string in snake_case.

    Examples:
        >>> camel_to_snake("helloWorld")
        'hello_world'
        >>> camel_to_snake("HelloWorld")
        'hello_world'
    """
    import re
    # Insert underscore before capital letters, then lowercase
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", camel_str)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text.

    Args:
        text: Input string possibly containing ANSI codes.

    Returns:
        String with ANSI codes removed.
    """
    import re
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_escape.sub("", text)


def dedent(text: str) -> str:
    """Remove common leading whitespace from all lines.

    Args:
        text: Multi-line string.

    Returns:
        Dedented string.
    """
    import textwrap
    return textwrap.dedent(text)


def shorten(text: str, max_length: int, placeholder: str = "...") -> str:
    """Shorten text to a maximum length, preserving word boundaries.

    Args:
        text: Input string.
        max_length: Maximum length of returned string.
        placeholder: String to append when truncated.

    Returns:
        Shortened string.
    """
    import textwrap
    return textwrap.shorten(text, max_length, placeholder=placeholder)


def extract_version(text: str) -> str | None:
    """Extract semantic version from text (e.g., 'v1.2.3' or '1.2.3').

    Args:
        text: Input string.

    Returns:
        Version string if found, None otherwise.
    """
    import re
    match = re.search(r"v?(\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?(?:\+[a-zA-Z0-9.-]+)?)", text)
    return match.group(1) if match else None
