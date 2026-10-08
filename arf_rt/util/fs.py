"""Filesystem utilities for ARF-RT (spec §19).

Provides:
  - atomic_write: temp → fsync → rename pattern for crash-safe writes
  - safe_path: resolves and validates paths against directory traversal
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from arf_rt.util.canon import ARFValidationError


def atomic_write(target: str | Path, data: bytes) -> None:
    """Write data to target atomically via temp → fsync → rename.

    Guarantees that target is never partially written: either the old
    content or the new content is present, never a mix.

    Args:
        target: Destination file path.
        data: Bytes to write.

    Raises:
        ARFValidationError: If target path is invalid.
        OSError: If filesystem operations fail.
    """
    target = Path(target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=str(target.parent),
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    try:
        os.write(fd, data)
        os.fsync(fd)
        os.close(fd)
        fd = -1  # Mark as closed
        os.replace(tmp_path, str(target))
    except BaseException:
        if fd >= 0:
            os.close(fd)
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def safe_resolve(base_dir: str | Path, untrusted_path: str) -> Path:
    """Resolve an untrusted path relative to base_dir, rejecting traversal.

    Args:
        base_dir: The trusted root directory.
        untrusted_path: A user-supplied relative path.

    Returns:
        Resolved absolute Path guaranteed to be under base_dir.

    Raises:
        ARFValidationError: If the resolved path escapes base_dir.
    """
    base = Path(base_dir).resolve()
    # Join and resolve to collapse .., symlinks, etc.
    resolved = (base / untrusted_path).resolve()

    # The resolved path must start with the base directory
    try:
        resolved.relative_to(base)
    except ValueError:
        raise ARFValidationError(
            f"Path traversal detected: '{untrusted_path}' resolves outside "
            f"base directory '{base}'"
        )

    return resolved
