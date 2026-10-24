"""
arf_rt/util/temporal_cache.py - Bounded LRU cache for path feasibility verdicts.

Memoizes temporal evaluation outcomes for path segments and prefixes to eliminate
redundant constraint evaluations during large-scale graph search.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from arf_rt.temporal.verdict import TemporalVerdict


@dataclass
class CacheStatistics:
    """Metrics for evaluation cache performance."""
    hits: int = 0
    misses: int = 0
    evictions: int = 0

    @property
    def total_requests(self) -> int:
        return self.hits + self.misses

    @property
    def hit_ratio(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.hits / self.total_requests


class TemporalVerdictCache:
    """
    Fixed-capacity LRU cache mapping canonical path tuples to TemporalVerdict results.
    """

    def __init__(self, max_size: int = 1000) -> None:
        if max_size <= 0:
            raise ValueError("max_size must be positive.")
        self.max_size = max_size
        self._cache: OrderedDict[tuple[str, ...], TemporalVerdict] = OrderedDict()
        self.stats = CacheStatistics()

    def get(self, path: list[str] | tuple[str, ...]) -> TemporalVerdict | None:
        """Retrieve cached verdict for path. Returns None on cache miss."""
        key = tuple(path)
        if key in self._cache:
            self.stats.hits += 1
            self._cache.move_to_end(key)
            return self._cache[key]

        self.stats.misses += 1
        return None

    def put(self, path: list[str] | tuple[str, ...], verdict: TemporalVerdict) -> None:
        """Store verdict in cache with LRU eviction when capacity is exceeded."""
        key = tuple(path)
        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = verdict
            return

        if len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)  # evict least recently used
            self.stats.evictions += 1

        self._cache[key] = verdict

    def clear(self) -> None:
        """Clear all entries and reset stats."""
        self._cache.clear()
        self.stats = CacheStatistics()

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, path: list[str] | tuple[str, ...]) -> bool:
        return tuple(path) in self._cache
