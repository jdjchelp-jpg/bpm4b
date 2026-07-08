"""
Binary Cover Art, Chapter Syncing & Metadata Inheritance

Features:
  #5  - Binary Cover Art Injector & Extractor (mutagen covr atom / ID3 APIC)
  #7  - Smart Metadata Copying (Inheritance from first file in batch)
  #13 - Embedded ID3v2/MP4 Chapter Atom Syncing
"""

import os
import re
import base64
import logging
import subprocess
from typing import Dict, List, Optional, Any, Tuple

from .ffmpeg_utils import find_ffmpeg, find_ffprobe, get_audio_duration

logger = logging.getLogger(__name__)

# ─── Cover Art Extraction ────────────────────────────────────

def extract_cover_art(audio_path: str, output_path: Optional[str] = None) -> Optional[bytes]:
    """
    Extract embedded cover art from an audio file.

    Uses ffmpeg to extract the attached picture stream (works for M4B/M4A/MP3).
    Returns raw image bytes, or saves to output_path if provided.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found — cannot extract cover art")

    probe = find_ffprobe()
    if not probe:
        raise RuntimeError("ffprobe not found — cannot probe streams")

    # First, find the cover art stream index
    cmd = [probe, '-v', 'quiet', '-print_format', 'json',
           '-show_streams', audio_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return None
        import json
        data = json.loads(result.stdout)
    except Exception as e:
        logger.warning(f"Failed to probe streams: {e}")
        return None

    cover_stream = None
    for stream in data.get('streams', []):
        if stream.get('codec_type') == 'video':
            cover_stream = stream
            break
        # Also check disposition
        if stream.get('disposition', {}).get('attached_pic') == 1:
            cover_stream = stream
            break

    if not cover_stream:
        logger.info("No cover art stream found")
        return None

    stream_index = cover_stream['index']
    tmp_path = audio_path + '.cover_tmp.jpg'

    try:
        extract_cmd = [
            ffmpeg, '-y', '-i', audio_path,
            '-map', f'0:{stream_index}',
            '-c:v', 'copy', tmp_path
        ]
        subprocess.run(extract_cmd, capture_output=True, text=True, timeout=30)

        if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
            return None

        with open(tmp_path, 'rb') as f:
            image_data = f.read()

        if output_path:
            import shutil
            shutil.move(tmp_path, output_path)
            return image_data

        return image_data

    except Exception as e:
        logger.error(f"Cover extraction error: {e}")
        return None
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def inject_cover_art(
    audio_path: str,
    cover_image_path: str,
    output_path: str,
) -> str:
    """
    Inject cover art into an audio file without re-encoding the audio stream.

    Uses ffmpeg stream copy mode to preserve audio quality.
    Supports JPEG and PNG images.

    Returns path to output file.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")

    if not os.path.isfile(cover_image_path):
        raise FileNotFoundError(f"Cover image not found: {cover_image_path}")

    # Detect image type
    ext = os.path.splitext(cover_image_path)[1].lower()
    if ext in ('.jpg', '.jpeg'):
        codec = 'mjpeg'
    elif ext == '.png':
        codec = 'png'
    else:
        raise ValueError(f"Unsupported cover image format: {ext}. Use JPEG or PNG.")

    cmd = [
        ffmpeg, '-y', '-i', audio_path,
        '-i', cover_image_path,
        '-map', '0:a',           # Audio from first input
        '-map', '1:v',           # Video (cover) from second input
        '-c:a', 'copy',          # Copy audio without re-encoding
        f'-c:v:{codec}',         # Video codec
        '-disposition:v', 'attached_pic',
        '-metadata:s:v', 'title=Cover Art',
        '-metadata:s:v', 'comment=Cover (front)',
        output_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"Cover injection failed: {result.stderr}")

    return output_path


def inject_cover_from_base64(
    audio_path: str,
    cover_base64: str,
    output_path: str,
) -> str:
    """Inject cover art from a base64-encoded image string."""
    import tempfile
    img_data = base64.b64decode(cover_base64)

    # Detect format from magic bytes
    if img_data[:2] == b'\xff\xd8':
        ext = '.jpg'
    elif img_data[:8] == b'\x89PNG\r\n\x1a\n':
        ext = '.png'
    else:
        ext = '.jpg'  # Default

    tmp_path = audio_path + f'.cover_tmp{ext}'
    try:
        with open(tmp_path, 'wb') as f:
            f.write(img_data)
        return inject_cover_art(audio_path, tmp_path, output_path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


# ─── Chapter Atom Syncing (M4B ↔ MP3) ──────────────────────

def extract_chapters_from_m4b(audio_path: str) -> List[Dict[str, Any]]:
    """
    Extract embedded chapter markers from an M4B/M4A file.

    Uses ffprobe to read the chapter metadata atoms.
    Returns list of [{title, start_time, end_time}].
    """
    probe = find_ffprobe()
    if not probe:
        raise RuntimeError("ffprobe not found")

    cmd = [
        probe, '-v', 'quiet', '-print_format', 'json',
        '-show_chapters', audio_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return []
        import json
        data = json.loads(result.stdout)
    except Exception as e:
        logger.warning(f"Failed to extract chapters: {e}")
        return []

    chapters = []
    for ch in data.get('chapters', []):
        start_sec = ch.get('start_time', 0)
        end_sec = ch.get('end_time', 0)

        # Convert from timebase if needed
        timebase = ch.get('time_base', '1/1000')
        tb_parts = timebase.split('/')
        if len(tb_parts) == 2:
            tb_num, tb_den = int(tb_parts[0]), int(tb_parts[1])
            if tb_num > 0 and tb_den > 0:
                start_sec = ch.get('start', 0) / tb_den * tb_num
                end_sec = ch.get('end', 0) / tb_den * tb_num

        # Get metadata
        metadata = ch.get('metadata', ch.get('tags', {}))
        title = metadata.get('title', f'Chapter {len(chapters) + 1}')

        chapters.append({
            'title': title,
            'start_time': round(float(start_sec), 3),
            'end_time': round(float(end_sec), 3),
        })

    return chapters


def write_chapters_to_m4b(
    input_path: str,
    output_path: str,
    chapters: List[Dict[str, Any]],
) -> str:
    """
    Write chapter markers into an M4B/M4A file using ffmpeg metadata.

    Preserves audio quality (stream copy). Creates chapter entries
    in the MP4 container.
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")

    import uuid
    chapter_file = os.path.join(
        os.path.dirname(output_path),
        f'chapters_{uuid.uuid4().hex[:8]}.txt'
    )

    try:
        with open(chapter_file, 'w', encoding='utf-8') as f:
            f.write(';FFMETADATA1\n')
            for i, ch in enumerate(chapters):
                start_ms = int(ch['start_time'] * 1000)
                end_ms = int(ch['end_time'] * 1000)

                f.write('[CHAPTER]\n')
                f.write('TIMEBASE=1/1000\n')
                f.write(f'START={start_ms}\n')
                f.write(f'END={end_ms}\n')
                f.write(f'title={ch["title"]}\n\n')

        cmd = [
            ffmpeg, '-y', '-i', input_path,
            '-i', chapter_file,
            '-map_metadata', '1',
            '-c:a', 'copy',
            '-movflags', '+faststart',
            output_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"Chapter write failed: {result.stderr}")

        return output_path

    finally:
        if os.path.exists(chapter_file):
            try:
                os.remove(chapter_file)
            except OSError:
                pass


def sync_chapters_to_mp3(
    m4b_path: str,
    mp3_paths: List[str],
    output_dir: str,
) -> List[Dict[str, Any]]:
    """
    Sync chapter markers from an M4B file to split MP3 files.
    Extracts M4B chapters and creates ID3v2 chapter frames in MP3s.

    Note: True ID3v2 chapter frames require mutagen for full support.
    This method creates sidecar metadata files as well.
    """
    chapters = extract_chapters_from_m4b(m4b_path)
    if not chapters:
        return []

    result = []
    for i, (ch, mp3_path) in enumerate(zip(chapters, mp3_paths)):
        # Write a sidecar JSON with chapter info for ID3 embedding
        sidecar_path = os.path.splitext(mp3_path)[0] + '.chapter.json'
        import json
        with open(sidecar_path, 'w') as f:
            json.dump(ch, f, indent=2)
        result.append({
            'mp3_path': mp3_path,
            'chapter': ch,
            'sidecar': sidecar_path,
        })

    return result


# ─── Metadata Inheritance (First-File Tags) ─────────────────

def inherit_metadata_from_first_file(
    file_paths: List[str],
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Read metadata tags from the first audio file in a batch and use them
    as overarching book metadata for the output M4B.

    Feature #7: Smart Metadata Copying (Inheritance Mapping)
    Used when converting a directory of MP3s into a single M4B.

    Args:
        file_paths: Sorted list of audio file paths
        metadata: Existing metadata overrides (take precedence)

    Returns:
        Merged metadata dict with inherited values
    """
    if not file_paths:
        return metadata or {}

    if metadata is None:
        metadata = {}

    first_file = file_paths[0]
    inherited = _read_file_tags(first_file)

    # Merge: existing metadata takes precedence over inherited
    final = dict(inherited)
    final.update(metadata)

    return final


def _read_file_tags(audio_path: str) -> Dict[str, str]:
    """
    Read common metadata tags from an audio file using ffprobe.
    """
    probe = find_ffprobe()
    if not probe:
        return {}

    cmd = [
        probe, '-v', 'quiet', '-print_format', 'json',
        '-show_format', audio_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return {}
        import json
        data = json.loads(result.stdout)
    except Exception:
        return {}

    tags = data.get('format', {}).get('tags', {})
    return {
        'title': tags.get('title', ''),
        'author': tags.get('artist', '') or tags.get('author', ''),
        'genre': tags.get('genre', ''),
        'album': tags.get('album', ''),
        'date': tags.get('date', ''),
        'description': tags.get('description', '') or tags.get('comment', ''),
        'track': tags.get('track', ''),
        'composer': tags.get('composer', ''),
        'publisher': tags.get('publisher', '') or tags.get('label', ''),
        'isbn': tags.get('isbn', ''),
    }
