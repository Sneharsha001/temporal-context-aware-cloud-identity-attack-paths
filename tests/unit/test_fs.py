"""Tests for ARF-RT filesystem utilities.

Covers:
  - Atomic write (temp → fsync → rename)
  - Safe path resolution (directory traversal rejection)
"""

import os
import tempfile

import pytest

from arf_rt.util.canon import ARFValidationError
from arf_rt.util.fs import atomic_write, safe_resolve


class TestAtomicWrite:
    """Tests for atomic_write()."""

    def test_creates_file_with_correct_content(self, tmp_path):
        target = tmp_path / "test.db"
        data = b"hello world"
        atomic_write(target, data)
        assert target.read_bytes() == data

    def test_overwrites_existing_file(self, tmp_path):
        target = tmp_path / "test.db"
        target.write_bytes(b"old content")
        atomic_write(target, b"new content")
        assert target.read_bytes() == b"new content"

    def test_creates_parent_directories(self, tmp_path):
        target = tmp_path / "sub" / "dir" / "test.db"
        atomic_write(target, b"data")
        assert target.read_bytes() == b"data"

    def test_no_temp_file_left_on_success(self, tmp_path):
        target = tmp_path / "test.db"
        atomic_write(target, b"data")
        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].name == "test.db"

    def test_empty_data(self, tmp_path):
        target = tmp_path / "empty.db"
        atomic_write(target, b"")
        assert target.read_bytes() == b""

    def test_large_data(self, tmp_path):
        target = tmp_path / "large.db"
        data = b"x" * (1024 * 1024)  # 1 MB
        atomic_write(target, data)
        assert target.read_bytes() == data


class TestSafeResolve:
    """Tests for safe_resolve()."""

    def test_simple_relative_path(self, tmp_path):
        result = safe_resolve(tmp_path, "file.txt")
        assert result == tmp_path / "file.txt"

    def test_nested_relative_path(self, tmp_path):
        result = safe_resolve(tmp_path, "sub/dir/file.txt")
        assert result == tmp_path / "sub" / "dir" / "file.txt"

    def test_rejects_parent_traversal(self, tmp_path):
        with pytest.raises(ARFValidationError, match="Path traversal"):
            safe_resolve(tmp_path, "../../../etc/passwd")

    def test_rejects_dot_dot_in_middle(self, tmp_path):
        with pytest.raises(ARFValidationError, match="Path traversal"):
            safe_resolve(tmp_path, "sub/../../etc/passwd")

    def test_rejects_absolute_path_outside(self, tmp_path):
        with pytest.raises(ARFValidationError, match="Path traversal"):
            safe_resolve(tmp_path, "/etc/passwd")

    def test_allows_dot_in_name(self, tmp_path):
        result = safe_resolve(tmp_path, "file.with.dots.txt")
        assert result == tmp_path / "file.with.dots.txt"

    def test_current_dir_dot(self, tmp_path):
        result = safe_resolve(tmp_path, "./file.txt")
        assert result == tmp_path / "file.txt"
