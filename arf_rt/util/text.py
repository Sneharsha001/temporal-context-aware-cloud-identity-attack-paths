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
