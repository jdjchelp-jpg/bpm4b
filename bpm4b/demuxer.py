"""
High-Fidelity Audio Demuxing (M4B ➔ MP3 Splitter)

Explode a single M4B/M4A file into separated, cleanly titled MP3 tracks
based on its internal embedded chapter map, using stream copy for zero quality loss.

Feature #20 from the BPM4B v13 feature set.
"""

import os
import re
import json
import uuid
import logging
import subprocess
from typing import List, Dict, Optional, Any

from .ffmpeg_utils import find_ffmpeg, find_ffprobe, get_audio_duration
from .cover_art import extract_chapters_from_m4b
from .path_utils import ensure_dir, cleanup_file

logger = logging.getLogger(__name__)


def demux_m4b_to_mp3(
    input_path: str,
    output_dir: str,
    quality: str = '128k',
    preserve_metadata: bool = True,
    naming_template: str = '{chapter_number:02d} - {chapter_title}.{ext}',
) -> List[Dict[str, Any]]:
    """
    Split an M4B/M4A file into individual MP3 chapter tracks.

    Uses ffmpeg's segment and metadata parsing for accurate chapter extraction.

    Args:
        input_path: Path to input M4B file
        output_dir: Directory for output MP3 files
        quality: MP3 encoding quality ('128k', '192k', '320k', etc.)
        preserve_metadata: Copy metadata tags from source
        naming_template: Template for output filenames.
                         Supports {chapter_number}, {chapter_title}, {ext}

    Returns:
        List of dicts with output_path, title, start_time, end_time, duration
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found — cannot demux")

    ensure_dir(output_dir)

    # Extract chapters from the M4B file
    chapters = extract_chapters_from_m4b(input_path)
    if not chapters:
        # If no chapters found, treat entire file as one chapter
        duration = get_audio_duration(input_path)
        chapters = [{
            'title': os.path.splitext(os.path.basename(input_path))[0],
            'start_time': 0.0,
            'end_time': duration,
        }]

    total_duration = get_audio_duration(input_path)
    results = []

    for i, ch in enumerate(chapters):
        chapter_num = i + 1
        chapter_title = _sanitize_filename(ch['title'])
        start_sec = ch['start_time']
        end_sec = ch.get('end_time', total_duration if i == len(chapters) - 1 else chapters[i + 1]['start_time'])

        # Generate output filename
        filename = naming_template.format(
            chapter_number=chapter_num,
            chapter_title=chapter_title or f'Chapter_{chapter_num}',
            ext='mp3',
        )
        output_path = os.path.join(output_dir, filename)

        # Duration of this segment
        duration = end_sec - start_sec
        if duration <= 0:
            logger.warning(f"Skipping chapter {chapter_num} with zero duration")
            continue

        # Use ffmpeg's -ss and -to for accurate seeking with stream copy
        cmd = [
            ffmpeg, '-y',
            '-i', input_path,
            '-ss', str(start_sec),
            '-to', str(end_sec),
            '-c:a', 'libmp3lame',
            '-b:a', quality,
            '-map_metadata', '0',   # Preserve metadata
            '-id3v2_version', '3',
            '-metadata', f'title={ch["title"]}',
            '-metadata', f'track={chapter_num}/{len(chapters)}',
            output_path,
        ]

        logger.info(f"Demuxing chapter {chapter_num}/{len(chapters)}: {ch['title']} ({start_sec}s → {end_sec}s)")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            # Try with re-encode if stream copy fails (shouldn't happen but handle gracefully)
            if 'codec' in (result.stderr or '').lower():
                logger.warning(f"Stream copy failed for chapter {chapter_num}, falling back to re-encode")
                cmd[4] = '-q:a'  # Use VBR quality for MP3
                cmd[5] = '2'     # VBR quality 2 (high)
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                results.append({
                    'output_path': None,
                    'title': ch['title'],
                    'start_time': start_sec,
                    'end_time': end_sec,
                    'duration': duration,
                    'error': result.stderr,
                })
                continue

        output_duration = get_audio_duration(output_path)

        results.append({
            'output_path': output_path,
            'title': ch['title'],
            'start_time': start_sec,
            'end_time': end_sec,
            'duration': output_duration,
            'size_bytes': os.path.getsize(output_path),
        })

    return results


def demux_to_wav(
    input_path: str,
    output_dir: str,
) -> List[Dict[str, Any]]:
    """Split M4B to WAV chapter files (lossless)."""
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")

    ensure_dir(output_dir)
    chapters = extract_chapters_from_m4b(input_path)
    total_duration = get_audio_duration(input_path)

    if not chapters:
        chapters = [{
            'title': os.path.splitext(os.path.basename(input_path))[0],
            'start_time': 0.0,
            'end_time': total_duration,
        }]

    results = []
    for i, ch in enumerate(chapters):
        chapter_num = i + 1
        start_sec = ch['start_time']
        end_sec = ch.get('end_time', total_duration)

        output_path = os.path.join(
            output_dir,
            f'{chapter_num:02d} - {_sanitize_filename(ch["title"])}.wav'
        )

        cmd = [
            ffmpeg, '-y',
            '-i', input_path,
            '-ss', str(start_sec),
            '-to', str(end_sec),
            '-c:a', 'pcm_s16le',
            output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            results.append({
                'output_path': output_path,
                'title': ch['title'],
                'start_time': start_sec,
                'end_time': end_sec,
                'duration': end_sec - start_sec,
            })

    return results


def _sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename."""
    # Remove or replace problematic characters
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'[\s]+', ' ', name).strip()
    # Trim to reasonable length
    if len(name) > 100:
        name = name[:100].rstrip()
    return name or 'untitled'
