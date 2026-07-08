"""
Dynamic Concurrency Throttle Guard

Automatically adjusts the number of parallel FFmpeg workers based on
available system memory and CPU core counts to prevent system freezing.

Feature #21 from the BPM4B v13 feature set.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Core Detection ──────────────────────────────────────────

_CPU_COUNT: Optional[int] = None
_TOTAL_MEM_MB: Optional[int] = None


def get_cpu_count() -> int:
    """
    Get the number of logical CPU cores.
    Returns at least 1, and defaults to 4 if detection fails.
    """
    global _CPU_COUNT
    if _CPU_COUNT is not None:
        return _CPU_COUNT
    try:
        import multiprocessing
        _CPU_COUNT = multiprocessing.cpu_count()
    except (ImportError, NotImplementedError):
        _CPU_COUNT = 4
    return max(1, _CPU_COUNT)


def get_total_memory_mb() -> int:
    """
    Get total system memory in MB.
    Returns 4096 (4GB) as safe default if detection fails.
    """
    global _TOTAL_MEM_MB
    if _TOTAL_MEM_MB is not None:
        return _TOTAL_MEM_MB

    try:
        import psutil
        _TOTAL_MEM_MB = int(psutil.virtual_memory().total / (1024 * 1024))
        return _TOTAL_MEM_MB
    except ImportError:
        pass

    # Fallback methods per platform
    try:
        import subprocess
        import platform

        if platform.system() == 'Linux':
            result = subprocess.run(
                ['grep', 'MemTotal', '/proc/meminfo'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                import re
                m = re.search(r'(\d+)', result.stdout)
                if m:
                    _TOTAL_MEM_MB = int(m.group(1)) // 1024
                    return _TOTAL_MEM_MB

        elif platform.system() == 'Darwin':
            result = subprocess.run(
                ['sysctl', '-n', 'hw.memsize'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                _TOTAL_MEM_MB = int(result.stdout.strip()) // (1024 * 1024)
                return _TOTAL_MEM_MB

        elif platform.system() == 'Windows':
            result = subprocess.run(
                ['wmic', 'memorychip', 'get', 'capacity'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                lines = [l.strip() for l in result.stdout.split('\n') if l.strip()]
                capacities = [int(l) for l in lines[1:] if l.isdigit()]
                if capacities:
                    _TOTAL_MEM_MB = sum(capacities) // (1024 * 1024)
                    return _TOTAL_MEM_MB
    except Exception:
        pass

    _TOTAL_MEM_MB = 4096  # Safe default: 4 GB
    return _TOTAL_MEM_MB


def get_available_memory_mb() -> int:
    """
    Get currently available (free) system memory in MB.
    """
    try:
        import psutil
        return int(psutil.virtual_memory().available / (1024 * 1024))
    except ImportError:
        pass

    # Rough estimate: assume 50% of total is available
    return get_total_memory_mb() // 2


def get_memory_usage_pct() -> float:
    """
    Get current memory usage as a percentage (0-100).
    """
    try:
        import psutil
        return psutil.virtual_memory().percent
    except ImportError:
        return 50.0


# ─── Concurrency Recommendations ─────────────────────────────

# Estimated memory per FFmpeg process (MB)
# Higher for WAV encodes, lower for stream-copy operations
FFMPEG_MEMORY_PER_WORKER_MB = {
    'stream_copy': 50,
    'aac_encode': 150,
    'wav_encode': 200,
    'flac_encode': 180,
    'mp3_encode': 120,
    'silence_detect': 100,
    'tts': 500,  # Kokoro TTS workers need more memory
}


def recommend_concurrency(
    task_type: str = 'aac_encode',
    user_preferred: int = 0,
    max_workers: int = 32,
    max_memory_pct: float = 85.0,
) -> int:
    """
    Recommend the optimal number of parallel workers.

    Args:
        task_type: Type of task ('stream_copy', 'aac_encode', 'wav_encode', etc.)
        user_preferred: User's preferred concurrency (0 = auto)
        max_workers: Absolute upper limit
        max_memory_pct: Maximum memory usage percentage before throttling

    Returns:
        Recommended number of concurrent workers
    """
    if user_preferred > 0:
        return min(user_preferred, max_workers)

    cpu_count = get_cpu_count()
    total_mem_mb = get_total_memory_mb()
    available_mem_mb = get_available_memory_mb()

    mem_per_worker = FFMPEG_MEMORY_PER_WORKER_MB.get(task_type, 150)

    # CPU-limited estimate: max cores - 1 (reserve one for OS)
    cpu_based = max(1, cpu_count - 1)

    # Memory-limited estimate
    usable_mem = int(available_mem_mb * max_memory_pct / 100)
    mem_based = max(1, usable_mem // mem_per_worker)

    # Take the smaller of the two, capped at max
    recommended = min(cpu_based, mem_based, max_workers)

    logger.debug(
        f"Concurrency: CPU={cpu_based}, MEM={mem_based} "
        f"(total={total_mem_mb}MB, avail={available_mem_mb}MB, "
        f"per_worker={mem_per_worker}MB) → {recommended}"
    )

    return recommended


def concurrency_safe_ceiling(task_type: str = 'aac_encode') -> int:
    """
    Get the absolute safe ceiling for concurrency, accounting for
    current system load. Use this as a hard limit.
    """
    current_mem_pct = get_memory_usage_pct()

    if current_mem_pct > 90:
        return 1  # Danger zone — single process only
    elif current_mem_pct > 80:
        return max(1, recommend_concurrency(task_type) // 2)
    else:
        return recommend_concurrency(task_type)


# ─── Convenience ─────────────────────────────────────────────

def auto_concurrency(task_type: str = 'aac_encode') -> int:
    """
    One-liner convenience: get the recommended concurrency for a task type.
    """
    return recommend_concurrency(task_type)


def is_psutil_available() -> bool:
    """Check if psutil is installed for accurate memory monitoring."""
    try:
        import psutil
        return True
    except ImportError:
        return False


def get_system_summary() -> dict:
    """Return a human-readable summary of system resources."""
    cpu = get_cpu_count()
    mem_total = get_total_memory_mb()
    mem_avail = get_available_memory_mb()
    mem_pct = get_memory_usage_pct()

    def fmt_mb(mb):
        if mb >= 1024:
            return f'{mb / 1024:.1f} GB'
        return f'{mb} MB'

    return {
        'cpu_cores': cpu,
        'total_memory': fmt_mb(mem_total),
        'available_memory': fmt_mb(mem_avail),
        'memory_usage_pct': mem_pct,
        'recommended_concurrency': recommend_concurrency(),
        'psutil_available': is_psutil_available(),
    }
