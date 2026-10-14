"""
arf_rt/util/__init__.py - Utility sub-package for ARF-RT.

Re-exports the most commonly used utilities for convenient import:

    from arf_rt.util import retry, slugify, flatten_dict
"""

from arf_rt.util.retry import retry, RetryError
from arf_rt.util.text import slugify, truncate, indent_block
from arf_rt.util.structures import flatten_dict, deep_merge

__all__ = [
    "retry",
    "RetryError",
    "slugify",
    "truncate",
    "indent_block",
    "flatten_dict",
    "deep_merge",
]
