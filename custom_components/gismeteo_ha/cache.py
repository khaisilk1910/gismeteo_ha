# Copyright (c) 2019-2024, Andrey "Limych" Khrolenok
# Original work licensed under CC BY-NC-SA 4.0; see repository LICENSE.
"""Small, bounded, non-blocking and atomic on-disk cache for Gismeteo."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from pathlib import Path

_LOGGER = logging.getLogger(__name__)
_MAX_CACHE_BYTES = 2_000_000


class Cache:
    """Cache raw provider responses without blocking Home Assistant's event loop."""

    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)

    def _path(self, filename: str) -> Path:
        # Filenames are generated exclusively by the integration.
        if not filename or filename != Path(filename).name or ".." in filename:
            raise ValueError("Invalid cache filename")
        return self._directory / filename

    def _read(self, filename: str, max_age: float) -> tuple[str, float] | None:
        path = self._path(filename)
        try:
            stat = path.stat()
            age = max(0.0, time.time() - stat.st_mtime)
            if age > max_age or stat.st_size > _MAX_CACHE_BYTES:
                return None
            return path.read_text(encoding="utf-8"), age
        except (FileNotFoundError, OSError, UnicodeError) as exc:
            if not isinstance(exc, FileNotFoundError):
                _LOGGER.debug("Unable to read cache %s: %s", filename, exc)
            return None

    async def async_read(
        self, filename: str, max_age: float
    ) -> tuple[str, float] | None:
        """Read a fresh or explicitly bounded stale response."""
        return await asyncio.to_thread(self._read, filename, max_age)

    def _write(self, filename: str, content: str) -> None:
        if len(content.encode("utf-8")) > _MAX_CACHE_BYTES:
            return
        target = self._path(filename)
        temp_path: str | None = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=target.parent,
                prefix=".gismeteo-", suffix=".tmp", delete=False,
            ) as file:
                temp_path = file.name
                file.write(content)
            os.replace(temp_path, target)
        except OSError as exc:
            _LOGGER.warning("Gismeteo cache write failed (%s): %s", filename, exc)
        finally:
            if temp_path:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except OSError:
                    pass

    async def async_save(self, filename: str, content: str) -> None:
        """Write a validated response atomically in an executor thread."""
        await asyncio.to_thread(self._write, filename, content)
