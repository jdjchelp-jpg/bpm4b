"""
Conversion Chunk-Level Caching (Incremental Processing)

If a batch conversion gets interrupted or a single file changes,
only process the updated or missing items instead of re-encoding the entire batch.

Feature #19 from the BPM4B v13 feature set.
"""

import os
import json
import hashlib
import logging
from typing import Dict, List, Optional, Any, Set
from datetime import datetime

from .path_utils import cache_dir, ensure_dir

logger = logging.getLogger(__name__)


# ─── Hashing ──────────────────────────────────────────────────

def file_md5(file_path: str, chunk_size: int = 65536) -> str:
    """
    Compute MD5 hash of a file's content.
    Uses streaming to handle large files efficiently.
    """
    md5 = hashlib.md5()
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            md5.update(chunk)
    return md5.hexdigest()


def file_quick_hash(file_path: str) -> str:
    """
    Compute a quick hash from file metadata (size + mtime + first/last bytes).
    Much faster than full MD5 for large files.
    Used as a fast check before full hashing.
    """
    stat = os.stat(file_path)
    size = stat.st_size
    mtime = stat.st_mtime

    # Hash a sample of the file (first + last 4KB)
    md5 = hashlib.md5(f'{size}:{mtime}'.encode())
    with open(file_path, 'rb') as f:
        head = f.read(4096)
        md5.update(head)
        f.seek(max(0, size - 4096))
        tail = f.read(4096)
        md5.update(tail)

    return md5.hexdigest()


# ─── Cache Entry ─────────────────────────────────────────────

class CacheEntry:
    """Represents a single cached processing result."""

    def __init__(
        self,
        source_hash: str,
        source_path: str,
        output_path: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.source_hash = source_hash
        self.source_path = source_path
        self.output_path = output_path
        self.metadata = metadata or {}
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'source_hash': self.source_hash,
            'source_path': self.source_path,
            'output_path': self.output_path,
            'metadata': self.metadata,
            'timestamp': self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CacheEntry':
        entry = cls(
            data['source_hash'],
            data.get('source_path', ''),
            data.get('output_path', ''),
            data.get('metadata', {}),
        )
        entry.timestamp = data.get('timestamp', entry.timestamp)
        return entry


# ─── Cache Manager ───────────────────────────────────────────

class ConversionCache:
    """
    Manages incremental processing cache for batch conversions.

    Stores MD5 hashes → output paths + metadata in a JSON index.
    """

    def __init__(self, cache_path: Optional[str] = None):
        if cache_path is None:
            cache_path = str(cache_dir('bpm4b') / 'conversion_cache.json')
        self.cache_path = cache_path
        self._entries: Dict[str, CacheEntry] = {}
        self._dirty = False
        self._load()

    def _load(self) -> None:
        """Load cache from disk."""
        if not os.path.isfile(self.cache_path):
            self._entries = {}
            return
        try:
            with open(self.cache_path, 'r') as f:
                data = json.load(f)
            self._entries = {
                k: CacheEntry.from_dict(v) for k, v in data.items()
            }
            logger.debug(f"Loaded {len(self._entries)} cache entries from {self.cache_path}")
        except (json.JSONDecodeError, KeyError, FileNotFoundError) as e:
            logger.warning(f"Failed to load cache: {e}")
            self._entries = {}

    def _save(self) -> None:
        """Save cache to disk."""
        ensure_dir(os.path.dirname(self.cache_path))
        try:
            data = {k: v.to_dict() for k, v in self._entries.items()}
            with open(self.cache_path, 'w') as f:
                json.dump(data, f, indent=2)
            self._dirty = False
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    def flush(self) -> None:
        """Write pending changes to disk."""
        if self._dirty:
            self._save()

    def get(self, source_path: str, quick_check: bool = True) -> Optional[CacheEntry]:
        """
        Get cached result for a source file.

        Args:
            source_path: Path to source file
            quick_check: If True, use quick hash first (faster)

        Returns:
            CacheEntry if valid, None if not cached or source has changed
        """
        if not os.path.isfile(source_path):
            return None

        # Quick check first
        qhash = file_quick_hash(source_path)
        if qhash in self._entries:
            entry = self._entries[qhash]
            if os.path.isfile(entry.output_path):
                return entry

        # Full MD5 check
        if not quick_check:
            full_hash = file_md5(source_path)
            if full_hash in self._entries:
                entry = self._entries[full_hash]
                if os.path.isfile(entry.output_path):
                    return entry

        return None

    def put(
        self,
        source_path: str,
        output_path: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Cache a processing result.

        Args:
            source_path: Path to source file
            output_path: Path to output file
            metadata: Optional processing metadata

        Returns:
            The hash key used
        """
        if not os.path.isfile(source_path):
            raise FileNotFoundError(f"Source not found: {source_path}")

        qhash = file_quick_hash(source_path)
        full_hash = file_md5(source_path)

        entry = CacheEntry(full_hash, source_path, output_path, metadata or {})
        self._entries[qhash] = entry
        self._entries[full_hash] = entry
        self._dirty = True
        self.flush()

        return full_hash

    def invalidate(self, source_path: str) -> bool:
        """Remove cache entry for a source file."""
        if not os.path.isfile(source_path):
            return False

        qhash = file_quick_hash(source_path)
        if qhash in self._entries:
            entry = self._entries[qhash]
            full_hash = entry.source_hash
            self._entries.pop(qhash, None)
            self._entries.pop(full_hash, None)
            self._dirty = True
            self.flush()
            return True
        return False

    def clear(self) -> None:
        """Clear all cached entries."""
        self._entries.clear()
        self._dirty = True
        self.flush()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            'total_entries': len(self._entries),
            'unique_sources': len(set(
                e.source_hash for e in self._entries.values()
            )),
            'cache_path': self.cache_path,
            'cache_size_bytes': os.path.getsize(self.cache_path) if os.path.isfile(self.cache_path) else 0,
        }


# ─── Global Singleton ────────────────────────────────────────

_default_cache: Optional[ConversionCache] = None


def get_cache() -> ConversionCache:
    """Get or create the default conversion cache singleton."""
    global _default_cache
    if _default_cache is None:
        _default_cache = ConversionCache()
    return _default_cache


# ─── Batch Processing Helpers ───────────────────────────────

def get_cached_or_process(
    source_path: str,
    process_func,
    output_path: str = '',
    output_ext: str = '.wav',
    metadata: Optional[Dict[str, Any]] = None,
    force_reprocess: bool = False,
) -> str:
    """
    Check cache first; if miss, run process_func and cache the result.

    Args:
        source_path: Source file to process
        process_func: Callable(source_path, output_path) → output_path
        output_path: Pre-determined output path (auto-generated if empty)
        output_ext: Extension for auto-generated output path
        metadata: Processing metadata to store in cache
        force_reprocess: If True, skip cache and always reprocess

    Returns:
        Path to the output file
    """
    cache = get_cache()

    if not force_reprocess:
        cached = cache.get(source_path)
        if cached and os.path.isfile(cached.output_path):
            logger.info(f"Using cached result for {source_path}")
            return cached.output_path

    if not output_path:
        from .path_utils import temp_dir
        out_dir = temp_dir('bpm4b_cache_')
        os.rmdir(out_dir)  # remove dir, use as prefix
        output_path = os.path.join(
            os.path.dirname(source_path),
            f'.cache_{os.path.splitext(os.path.basename(source_path))[0]}{output_ext}'
        )

    # Run the processing function
    result_path = process_func(source_path, output_path)

    # Cache the result
    try:
        cache.put(source_path, result_path, metadata)
    except Exception as e:
        logger.warning(f"Failed to cache result: {e}")

    return result_path


def process_batch_cached(
    source_paths: List[str],
    process_func,
    output_dir: str,
    output_ext: str = '.wav',
    force_reprocess: bool = False,
) -> Dict[str, str]:
    """
    Process a batch of files with caching.
    Only processes files that haven't been cached yet.

    Args:
        source_paths: List of source files
        process_func: Callable(source_path, output_path) → output_path
        output_dir: Directory for output files
        output_ext: Extension for output files
        force_reprocess: If True, skip cache

    Returns:
        Dict mapping source_path → output_path
    """
    ensure_dir(output_dir)
    cache = get_cache()
    results = {}

    for source_path in source_paths:
        base = os.path.splitext(os.path.basename(source_path))[0]
        output_path = os.path.join(output_dir, f"{base}{output_ext}")

        if not force_reprocess:
            cached = cache.get(source_path)
            if cached and os.path.isfile(cached.output_path):
                results[source_path] = cached.output_path
                continue

        result_path = process_func(source_path, output_path)
        try:
            cache.put(source_path, result_path)
        except Exception:
            pass
        results[source_path] = result_path

    return results
