"""
Intelligent FFmpeg Path Discovery & Audio Analysis Utilities

Features:
  #8  - Intelligent FFmpeg Path Discovery (auto-find across platforms)
  #12 - Acoustic Silence-Based Auto-Chaptering
  #22 - Smart Border Silence Trimmer
  #23 - Pre-Flight Storage Capacity Estimator
"""

import os
import re
import sys
import json
import shutil
import logging
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from .path_utils import safe_path, is_windows, is_macos, is_linux

logger = logging.getLogger(__name__)

# ─── #8: Intelligent FFmpeg Path Discovery ───────────────────

_FFMPEG_CACHE: Optional[str] = None
_FFPROBE_CACHE: Optional[str] = None


def _find_binary(name: str) -> Optional[str]:
    """Search for a binary using `where` (Windows) or `which` (Unix)."""
    try:
        if is_windows():
            result = subprocess.run(
                ['where', name],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                path = result.stdout.strip().split('\n')[0].strip()
                if os.path.isfile(path):
                    return path
        else:
            result = subprocess.run(
                ['which', name],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                path = result.stdout.strip()
                if os.path.isfile(path):
                    return path
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def find_ffmpeg() -> Optional[str]:
    """
    Discover ffmpeg binary location.
    Checks: bundled path → system PATH → common install locations.
    """
    global _FFMPEG_CACHE
    if _FFMPEG_CACHE is not None:
        return _FFMPEG_CACHE

    # 1. Check if ffmpeg is in PATH via shutil
    path_in_path = shutil.which('ffmpeg')
    if path_in_path:
        _FFMPEG_CACHE = path_in_path
        return path_in_path

    # 2. Try `which`/`where`
    found = _find_binary('ffmpeg')
    if found:
        _FFMPEG_CACHE = found
        return found

    # 3. Common install locations by platform
    common_paths = []
    if is_windows():
        common_paths = [
            r'C:\ffmpeg\bin\ffmpeg.exe',
            r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
            os.path.expanduser(r'~\AppData\Local\ffmpeg\bin\ffmpeg.exe'),
            os.path.expanduser(r'~\scoop\apps\ffmpeg\current\bin\ffmpeg.exe'),
        ]
    elif is_macos():
        common_paths = [
            '/usr/local/bin/ffmpeg',
            '/opt/homebrew/bin/ffmpeg',
            '/opt/local/bin/ffmpeg',
        ]
    else:
        common_paths = [
            '/usr/bin/ffmpeg',
            '/usr/local/bin/ffmpeg',
        ]

    for p in common_paths:
        if os.path.isfile(p):
            _FFMPEG_CACHE = p
            return p

    # 4. Search in common parent directories
    search_roots = []
    if is_windows():
        search_roots = ['C:\\', os.path.expanduser('~')]
    else:
        search_roots = ['/usr', '/opt', os.path.expanduser('~')]

    for root in search_roots:
        for dirpath, dirnames, filenames in os.walk(root):
            if 'ffmpeg' in filenames or 'ffmpeg.exe' in filenames:
                candidate = os.path.join(dirpath, 'ffmpeg' if not is_windows() else 'ffmpeg.exe')
                if os.path.isfile(candidate):
                    _FFMPEG_CACHE = candidate
                    return candidate
            # Limit search depth to 3 to avoid slow scans
            depth = dirpath.replace(root, '').count(os.sep)
            if depth >= 3:
                dirnames.clear()

    _FFMPEG_CACHE = ''  # Mark as not found
    return None


def find_ffprobe() -> Optional[str]:
    """Discover ffprobe binary location using the same strategy."""
    global _FFPROBE_CACHE
    if _FFPROBE_CACHE is not None:
        return _FFPROBE_CACHE

    path_in_path = shutil.which('ffprobe')
    if path_in_path:
        _FFPROBE_CACHE = path_in_path
        return path_in_path

    found = _find_binary('ffprobe')
    if found:
        _FFPROBE_CACHE = found
        return found

    _FFPROBE_CACHE = ''
    return None


def get_ffmpeg_info() -> Dict[str, Any]:
    """Return detailed ffmpeg availability info."""
    ffmpeg_path = find_ffmpeg()
    if not ffmpeg_path:
        return {'available': False, 'path': None, 'version': None, 'error': 'ffmpeg not found'}

    try:
        result = subprocess.run(
            [ffmpeg_path, '-version'],
            capture_output=True, text=True, timeout=10
        )
        version = result.stdout.split('\n')[0] if result.returncode == 0 else 'unknown'
        return {'available': True, 'path': ffmpeg_path, 'version': version, 'error': None}
    except Exception as e:
        return {'available': False, 'path': ffmpeg_path, 'version': None, 'error': str(e)}


def check_ffmpeg_compat() -> Dict[str, bool]:
    """Check if ffmpeg has the features BPM4B needs."""
    ffmpeg = find_ffmpeg()
    compat = {
        'available': ffmpeg is not None,
        'concat_demuxer': False,
        'silencedetect_filter': False,
        'silenceremove_filter': False,
        'aac_encoder': False,
        'libmp3lame': False,
    }
    if not ffmpeg:
        return compat

    try:
        result = subprocess.run(
            [ffmpeg, '-filters'],
            capture_output=True, text=True, timeout=15
        )
        filters = result.stdout + result.stderr
        compat['silencedetect_filter'] = 'silencedetect' in filters
        compat['silenceremove_filter'] = 'silenceremove' in filters

        encoders_result = subprocess.run(
            [ffmpeg, '-encoders'],
            capture_output=True, text=True, timeout=15
        )
        encoders = encoders_result.stdout + encoders_result.stderr
        compat['aac_encoder'] = 'aac' in encoders
        compat['libmp3lame'] = 'libmp3lame' in encoders

        # Concat demuxer is built-in, assume available
        compat['concat_demuxer'] = True
    except Exception:
        pass

    return compat


# ─── Audio Analysis Helpers ──────────────────────────────────

def get_audio_duration(audio_path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    ffprobe = find_ffprobe()
    if not ffprobe:
        return 0.0

    cmd = [ffprobe, '-v', 'quiet', '-print_format', 'json',
           '-show_format', '-show_streams', audio_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            duration = data.get('format', {}).get('duration')
            if duration:
                return float(duration)
    except Exception:
        pass

    # Fallback: parse ffmpeg stderr
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return 0.0
    try:
        result = subprocess.run(
            [ffmpeg, '-i', audio_path, '-hide_banner'],
            capture_output=True, text=True, timeout=30
        )
        output = result.stdout + result.stderr
        m = re.search(r'Duration:\s*(\d+):(\d+):(\d+)\.(\d+)', output)
        if m:
            h, mn, s, cs = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            return h * 3600 + mn * 60 + s + cs / 100
    except Exception:
        pass
    return 0.0


def get_audio_bitrate(audio_path: str) -> Optional[int]:
    """Get audio bitrate in kbps."""
    ffprobe = find_ffprobe()
    if not ffprobe:
        return None
    cmd = [ffprobe, '-v', 'quiet', '-print_format', 'json',
           '-show_format', audio_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            bitrate = data.get('format', {}).get('bit_rate')
            if bitrate:
                return int(bitrate) // 1000
    except Exception:
        pass
    return None


def get_sample_rate(audio_path: str) -> Optional[int]:
    """Get audio sample rate."""
    ffprobe = find_ffprobe()
    if not ffprobe:
        return None
    cmd = [ffprobe, '-v', 'quiet', '-print_format', 'json',
           '-show_streams', audio_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            for stream in data.get('streams', []):
                sr = stream.get('sample_rate')
                if sr:
                    return int(sr)
    except Exception:
        pass
    return None


# ─── #12: Acoustic Silence-Based Auto-Chaptering ─────────────

def detect_silence_regions(
    audio_path: str,
    noise_threshold: str = '-30dB',
    min_silence_duration: float = 2.0,
) -> List[Dict[str, float]]:
    """
    Scan audio file for natural silence regions using ffmpeg's silencedetect filter.

    Args:
        audio_path: Path to audio file
        noise_threshold: Noise floor threshold (e.g., '-30dB', '-40dB')
        min_silence_duration: Minimum silence duration in seconds

    Returns:
        List of dicts: [{start, end, duration}] in seconds
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found — cannot perform silence detection")

    cmd = [
        ffmpeg, '-i', audio_path,
        '-af', f'silencedetect=noise={noise_threshold}:d={min_silence_duration}',
        '-f', 'null', '-'
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        logger.error("Silence detection timed out")
        return []
    except Exception as e:
        logger.error(f"Silence detection failed: {e}")
        return []

    events = []
    silence_start = None
    for line in output.split('\n'):
        if 'silence_start' in line:
            m = re.search(r'silence_start:\s*([\d.]+)', line)
            if m:
                silence_start = float(m.group(1))
        elif 'silence_end' in line:
            m = re.search(r'silence_end:\s*([\d.]+)\s*\|\s*silence_duration:\s*([\d.]+)', line)
            if m and silence_start is not None:
                events.append({
                    'start': silence_start,
                    'end': float(m.group(1)),
                    'duration': float(m.group(2)),
                })
                silence_start = None

    return events


def auto_chapter_from_silence(
    audio_path: str,
    noise_threshold: str = '-30dB',
    min_silence_duration: float = 2.0,
    min_chapter_duration: float = 60.0,
    max_chapter_count: int = 200,
) -> List[Dict[str, Any]]:
    """
    Generate chapter markers from silence regions in an audio file.

    Args:
        audio_path: Path to audio file
        noise_threshold: Noise floor for silence detection
        min_silence_duration: Minimum silence to consider a chapter break (sec)
        min_chapter_duration: Minimum chapter length (ignore shorter segments)
        max_chapter_count: Maximum number of chapters to generate

    Returns:
        List of chapter dicts: [{title, start_time, end_time}]
    """
    total_duration = get_audio_duration(audio_path)
    if total_duration <= 0:
        return []

    silence_events = detect_silence_regions(
        audio_path, noise_threshold, min_silence_duration
    )

    if not silence_events:
        return [{'title': 'Full Audio', 'start_time': 0.0, 'end_time': total_duration}]

    chapters = []
    last_end = 0.0
    chapter_count = 0

    for event in silence_events:
        chapter_start = last_end
        chapter_end = event['start']

        if chapter_end - chapter_start >= min_chapter_duration:
            chapter_count += 1
            if chapter_count > max_chapter_count:
                break
            chapters.append({
                'title': f'Chapter {chapter_count}',
                'start_time': round(chapter_start, 3),
                'end_time': round(chapter_end, 3),
            })
            last_end = event['end']

    # Final chapter (audio after last silence)
    if total_duration - last_end >= min_chapter_duration and chapter_count < max_chapter_count:
        chapters.append({
            'title': f'Chapter {chapter_count + 1}',
            'start_time': round(last_end, 3),
            'end_time': round(total_duration, 3),
        })

    return chapters


# ─── #22: Smart Border Silence Trimmer ───────────────────────

def trim_border_silence(
    input_path: str,
    output_path: str,
    noise_threshold: str = '-50dB',
    min_silence_duration: float = 0.1,
) -> str:
    """
    Strip leading and trailing silence from an audio file using ffmpeg.

    Args:
        input_path: Source audio file
        output_path: Destination audio file
        noise_threshold: Noise floor threshold
        min_silence_duration: Minimum silence to remove

    Returns:
        Path to trimmed output file
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found — cannot trim silence")

    # Remove leading silence, then trailing silence
    cmd = [
        ffmpeg, '-y', '-i', input_path,
        '-af', (
            f'silenceremove=start_periods=1:'
            f'start_duration={min_silence_duration}:'
            f'start_threshold={noise_threshold},'
            f'silenceremove=stop_periods=1:'
            f'stop_duration={min_silence_duration}:'
            f'stop_threshold={noise_threshold}'
        ),
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"Border silence trim failed: {result.stderr}")
    return output_path


def trim_all_silence(
    input_path: str,
    output_path: str,
    noise_threshold: str = '-50dB',
    min_silence_duration: float = 0.5,
) -> str:
    """
    Strip ALL silence (not just borders) from an audio file.
    Useful for removing dead air between chapters.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found — cannot trim silence")

    cmd = [
        ffmpeg, '-y', '-i', input_path,
        '-af', (
            f'silenceremove=start_periods=1:'
            f'start_duration={min_silence_duration}:'
            f'start_threshold={noise_threshold}:'
            f'stop_periods=0:'
            f'restart_periods=1:'
            f'restart_duration={min_silence_duration}:'
            f'restart_threshold={noise_threshold}'
        ),
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"Silence removal failed: {result.stderr}")
    return output_path


# ─── #23: Pre-Flight Storage Capacity Estimator ──────────────

def estimate_output_size(
    input_path: str,
    target_bitrate_kbps: int = 64,
    output_format: str = 'm4b',
) -> Dict[str, Any]:
    """
    Estimate the size of the output file before conversion.

    Args:
        input_path: Source audio file path
        target_bitrate_kbps: Target bitrate in kbps
        output_format: Output format (m4b, mp3, flac, etc.)

    Returns:
        dict with estimated size info
    """
    duration_seconds = get_audio_duration(input_path)
    if duration_seconds <= 0:
        return {
            'input_path': input_path,
            'duration': None,
            'estimated_size_bytes': None,
            'estimated_size_human': 'Unknown',
            'target_bitrate_kbps': target_bitrate_kbps,
            'error': 'Could not determine duration',
        }

    # ((bitrate_kbps * 1000) * duration_seconds) / 8 = bytes
    estimated_bytes = int((target_bitrate_kbps * 1000) * duration_seconds / 8)

    # Overhead for container (~10%)
    estimated_bytes = int(estimated_bytes * 1.1)

    return {
        'input_path': input_path,
        'duration_seconds': duration_seconds,
        'duration_human': _format_duration(duration_seconds),
        'estimated_size_bytes': estimated_bytes,
        'estimated_size_human': _format_bytes(estimated_bytes),
        'target_bitrate_kbps': target_bitrate_kbps,
        'output_format': output_format,
        'warning': _check_disk_space(estimated_bytes),
    }


def estimate_batch_output_size(
    input_paths: List[str],
    target_bitrate_kbps: int = 64,
    output_format: str = 'm4b',
) -> Dict[str, Any]:
    """Estimate total output size for multiple input files."""
    total_duration = 0.0
    per_file = []

    for path in input_paths:
        est = estimate_output_size(path, target_bitrate_kbps, output_format)
        total_duration += est.get('duration_seconds', 0) or 0
        per_file.append(est)

    total_bytes = sum(
        f.get('estimated_size_bytes', 0) or 0 for f in per_file
    )

    return {
        'files': per_file,
        'total_duration_seconds': total_duration,
        'total_duration_human': _format_duration(total_duration),
        'total_estimated_size_bytes': total_bytes,
        'total_estimated_size_human': _format_bytes(total_bytes),
        'target_bitrate_kbps': target_bitrate_kbps,
        'output_format': output_format,
        'warning': _check_disk_space(total_bytes),
    }


def _format_bytes(n: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if abs(n) < 1024:
            return f'{n:.1f} {unit}' if unit != 'B' else f'{n} {unit}'
        n /= 1024
    return f'{n:.1f} PB'


def _format_duration(seconds: float) -> str:
    """Format duration as human-readable string."""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f'{hours}h')
    if minutes:
        parts.append(f'{minutes}m')
    parts.append(f'{secs}s')
    return ' '.join(parts)


def _check_disk_space(needed_bytes: int) -> Optional[str]:
    """Check if there's enough disk space in temp/output dirs."""
    try:
        import shutil
        info = shutil.disk_usage(os.path.abspath('.'))
        if needed_bytes > info.free:
            shortage = needed_bytes - info.free
            return (
                f'Low disk space! Need {_format_bytes(needed_bytes)} '
                f'but only {_format_bytes(info.free)} available '
                f'(short {_format_bytes(shortage)}). Free up space first.'
            )
    except Exception:
        pass
    return None
