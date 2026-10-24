"""
tests/unit/test_temporal_cache.py - Unit tests for TemporalVerdictCache.

Validates LRU eviction semantics, hit/miss tracking, capacity enforcement,
and cache invalidation behaviour for bounded memoization of temporal verdicts.
"""

from __future__ import annotations

import pytest

from arf_rt.util.temporal_cache import CacheStatistics, TemporalVerdictCache
from arf_rt.temporal.verdict import TemporalVerdict, VerdictKind


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _verdict(feasible: bool, reason: str = "test") -> TemporalVerdict:
    kind = VerdictKind.FEASIBLE if feasible else VerdictKind.INFEASIBLE
    return TemporalVerdict(kind=kind, reason=reason)


# ---------------------------------------------------------------------------
# CacheStatistics tests
# ---------------------------------------------------------------------------

class TestCacheStatistics:
    def test_zero_total_requests(self):
        stats = CacheStatistics()
        assert stats.total_requests == 0

    def test_hit_ratio_zero_requests(self):
        stats = CacheStatistics()
        assert stats.hit_ratio == 0.0

    def test_hit_ratio_all_hits(self):
        stats = CacheStatistics(hits=10, misses=0)
        assert stats.hit_ratio == 1.0

    def test_hit_ratio_mixed(self):
        stats = CacheStatistics(hits=3, misses=7)
        assert abs(stats.hit_ratio - 0.3) < 1e-9

    def test_total_requests_sums_hits_and_misses(self):
        stats = CacheStatistics(hits=4, misses=6)
        assert stats.total_requests == 10


# ---------------------------------------------------------------------------
# TemporalVerdictCache - construction
# ---------------------------------------------------------------------------

class TestCacheConstruction:
    def test_default_max_size(self):
        cache = TemporalVerdictCache()
        assert cache.max_size == 1000

    def test_custom_max_size(self):
        cache = TemporalVerdictCache(max_size=50)
        assert cache.max_size == 50

    def test_zero_max_size_raises(self):
        with pytest.raises(ValueError):
            TemporalVerdictCache(max_size=0)

    def test_negative_max_size_raises(self):
        with pytest.raises(ValueError):
            TemporalVerdictCache(max_size=-1)

    def test_initial_length_zero(self):
        cache = TemporalVerdictCache()
        assert len(cache) == 0


# ---------------------------------------------------------------------------
# TemporalVerdictCache - basic get/put
# ---------------------------------------------------------------------------

class TestCacheGetPut:
    def test_miss_on_empty_cache(self):
        cache = TemporalVerdictCache()
        result = cache.get(["a", "b"])
        assert result is None
        assert cache.stats.misses == 1

    def test_put_and_get_returns_verdict(self):
        cache = TemporalVerdictCache()
        v = _verdict(True, "ok")
        cache.put(["a", "b"], v)
        result = cache.get(["a", "b"])
        assert result is v

    def test_hit_increments_hit_counter(self):
        cache = TemporalVerdictCache()
        cache.put(["x"], _verdict(True))
        cache.get(["x"])
        assert cache.stats.hits == 1
        assert cache.stats.misses == 0

    def test_miss_increments_miss_counter(self):
        cache = TemporalVerdictCache()
        cache.get(["nonexistent"])
        assert cache.stats.misses == 1
        assert cache.stats.hits == 0

    def test_tuple_and_list_keys_equivalent(self):
        cache = TemporalVerdictCache()
        v = _verdict(False, "expired")
        cache.put(("a", "b", "c"), v)
        assert cache.get(["a", "b", "c"]) is v

    def test_overwrite_existing_key(self):
        cache = TemporalVerdictCache()
        v1 = _verdict(True, "first")
        v2 = _verdict(False, "second")
        cache.put(["edge1"], v1)
        cache.put(["edge1"], v2)
        assert cache.get(["edge1"]) is v2
        assert len(cache) == 1

    def test_distinct_paths_stored_independently(self):
        cache = TemporalVerdictCache()
        v1 = _verdict(True)
        v2 = _verdict(False)
        cache.put(["a"], v1)
        cache.put(["b"], v2)
        assert cache.get(["a"]) is v1
        assert cache.get(["b"]) is v2


# ---------------------------------------------------------------------------
# TemporalVerdictCache - contains operator
# ---------------------------------------------------------------------------

class TestCacheContains:
    def test_not_contains_on_miss(self):
        cache = TemporalVerdictCache()
        assert ["z"] not in cache

    def test_contains_after_put(self):
        cache = TemporalVerdictCache()
        cache.put(["a", "b"], _verdict(True))
        assert ["a", "b"] in cache

    def test_tuple_contains(self):
        cache = TemporalVerdictCache()
        cache.put(("x", "y"), _verdict(False))
        assert ("x", "y") in cache


# ---------------------------------------------------------------------------
# TemporalVerdictCache - LRU eviction
# ---------------------------------------------------------------------------

class TestLRUEviction:
    def test_evicts_lru_when_full(self):
        cache = TemporalVerdictCache(max_size=3)
        cache.put(["a"], _verdict(True))
        cache.put(["b"], _verdict(True))
        cache.put(["c"], _verdict(True))
        cache.put(["d"], _verdict(True))  # should evict "a"
        assert cache.get(["a"]) is None
        assert cache.get(["b"]) is not None

    def test_eviction_increments_counter(self):
        cache = TemporalVerdictCache(max_size=2)
        cache.put(["a"], _verdict(True))
        cache.put(["b"], _verdict(True))
        cache.put(["c"], _verdict(True))
        assert cache.stats.evictions == 1

    def test_access_refreshes_recency(self):
        cache = TemporalVerdictCache(max_size=2)
        cache.put(["a"], _verdict(True))
        cache.put(["b"], _verdict(True))
        cache.get(["a"])  # refresh "a"
        cache.put(["c"], _verdict(True))  # should evict "b", not "a"
        assert cache.get(["a"]) is not None
        assert cache.get(["b"]) is None

    def test_length_capped_at_max_size(self):
        cache = TemporalVerdictCache(max_size=5)
        for i in range(10):
            cache.put([str(i)], _verdict(True))
        assert len(cache) == 5

    def test_multiple_evictions_counted(self):
        cache = TemporalVerdictCache(max_size=2)
        for i in range(6):
            cache.put([str(i)], _verdict(True))
        assert cache.stats.evictions == 4


# ---------------------------------------------------------------------------
# TemporalVerdictCache - clear
# ---------------------------------------------------------------------------

class TestCacheClear:
    def test_clear_empties_cache(self):
        cache = TemporalVerdictCache()
        cache.put(["a"], _verdict(True))
        cache.clear()
        assert len(cache) == 0

    def test_clear_resets_stats(self):
        cache = TemporalVerdictCache(max_size=1)
        cache.put(["a"], _verdict(True))
        cache.get(["a"])
        cache.put(["b"], _verdict(True))  # eviction
        cache.clear()
        assert cache.stats.hits == 0
        assert cache.stats.misses == 0
        assert cache.stats.evictions == 0

    def test_get_after_clear_is_miss(self):
        cache = TemporalVerdictCache()
        cache.put(["a"], _verdict(False))
        cache.clear()
        assert cache.get(["a"]) is None
        assert cache.stats.misses == 1
