"""
Multi-Format Chapter Import/Export

Supports CUE sheets, Audacity label files (.txt), and WebVTT (.vtt) chapter formats.

Feature #16 from the BPM4B v13 feature set.
"""

import re
import os
import logging
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)


# ─── Unified Chapter Format ──────────────────────────────────

ChapterList = List[Dict[str, Any]]
"""Internal chapter format: [{title, start_time (sec), end_time (sec)}]"""


# ═══════════════════════════════════════════════════════════════
# Import Parsers
# ═══════════════════════════════════════════════════════════════

def import_chapters(file_path: str) -> ChapterList:
    """
    Auto-detect and import chapters from a file.
    Supports .cue, .txt (Audacity labels), .vtt, .csv, .json formats.
    """
    ext = os.path.splitext(file_path)[1].lower()
    parsers = {
        '.cue': parse_cue_sheet,
        '.txt': parse_audacity_labels,
        '.vtt': parse_webvtt,
        '.csv': parse_csv_chapters,
        '.json': parse_json_chapters,
        '.chapters.txt': parse_audacity_labels,  # also check for .chapters.txt
    }

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # Try explicit extension match
    if ext in parsers:
        try:
            chapters = parsers[ext](content)
            if chapters:
                return chapters
        except Exception as e:
            logger.warning(f"Failed to parse as {ext}: {e}")

    # Auto-detect: try each parser
    for name, parser in parsers.items():
        try:
            chapters = parser(content)
            if chapters:
                logger.info(f"Auto-detected chapter format: {name}")
                return chapters
        except Exception:
            continue

    raise ValueError(
        f"Could not parse '{file_path}' — unsupported format. "
        "Supported: .cue, .txt (Audacity), .vtt, .csv, .json"
    )


# ─── CUE Sheet Parser ────────────────────────────────────────

def parse_cue_sheet(content: str) -> ChapterList:
    """
    Parse a .cue sheet into chapter list.

    CUE format:
      TRACK 01 AUDIO
        TITLE "Chapter Title"
        INDEX 01 00:00:00
      TRACK 02 AUDIO
        TITLE "Second Chapter"
        INDEX 01 03:45:30
    """
    chapters = []
    current_track = {}
    index_time = None

    for line in content.split('\n'):
        stripped = line.strip()

        if stripped.upper().startswith('TRACK') and 'AUDIO' in stripped.upper():
            if current_track and index_time is not None:
                chapters.append(current_track)
            current_track = {'title': f'Track {len(chapters) + 1}', 'start_time': index_time or 0.0}
            index_time = None

        elif stripped.upper().startswith('TITLE '):
            title = stripped[6:].strip().strip('"')
            current_track['title'] = title

        elif stripped.upper().startswith('INDEX'):
            parts = stripped.split()
            if len(parts) >= 3:
                time_str = parts[-1]
                try:
                    index_time = _parse_cue_time(time_str)
                    # Always update start_time from the INDEX line
                    current_track['start_time'] = index_time
                except ValueError:
                    continue

    if current_track and index_time is not None:
        chapters.append(current_track)

    # Calculate end times
    _calculate_end_times(chapters)
    return chapters


def _parse_cue_time(time_str: str) -> float:
    """Parse CUE time format (MM:SS:FF or MM:SS.FF)."""
    parts = re.split(r'[:.]', time_str)
    if len(parts) == 3:
        minutes, seconds, frames = int(parts[0]), int(parts[1]), int(parts[2])
        return minutes * 60 + seconds + frames / 75  # CD frames = 1/75 sec
    if len(parts) == 2:
        minutes, seconds = int(parts[0]), int(parts[1])
        return minutes * 60 + seconds
    if len(parts) == 1:
        return float(parts[0])
    raise ValueError(f"Invalid CUE time: {time_str}")


# ─── Audacity Label Parser ───────────────────────────────────

def parse_audacity_labels(content: str) -> ChapterList:
    """
    Parse Audacity label format (.txt).
    Each line: <start> <end> <label>
    or:        <start> <label>  (point label)
    """
    chapters = []
    for line in content.split('\n'):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue

        parts = stripped.split('\t')
        if len(parts) < 2:
            parts = stripped.split()

        if len(parts) >= 2:
            try:
                start = float(parts[0])
            except ValueError:
                continue

            if len(parts) >= 3:
                try:
                    end = float(parts[1])
                    label = ' '.join(parts[2:])
                except ValueError:
                    end = start
                    label = ' '.join(parts[1:])
            else:
                end = start
                label = ' '.join(parts[1:])

            chapters.append({
                'title': label.strip() or f'Chapter {len(chapters) + 1}',
                'start_time': start,
                'end_time': end,
            })

    _calculate_end_times(chapters)
    return chapters


# ─── WebVTT Parser ───────────────────────────────────────────

def parse_webvtt(content: str) -> ChapterList:
    """
    Parse WebVTT (.vtt) chapter format.

    WEBVTT

    00:00:00.000 --> 00:03:45.500
    Chapter 1 Title

    00:03:45.500 --> 00:08:12.300
    Chapter 2 Title
    """
    chapters = []
    lines = content.split('\n')
    i = 0

    # Skip WEBVTT header
    while i < len(lines) and not re.search(r'\d+:\d+', lines[i]):
        i += 1

    while i < len(lines):
        line = lines[i].strip()

        # Timestamp line
        ts_match = re.match(
            r'(\d+:\d+:\d+\.\d+|\d+:\d+\.\d+)\s*-->\s*(\d+:\d+:\d+\.\d+|\d+:\d+\.\d+)',
            line
        )
        if ts_match:
            start = _parse_vtt_time(ts_match.group(1))
            end = _parse_vtt_time(ts_match.group(2))

            # Next non-empty line is the title
            title = f'Chapter {len(chapters) + 1}'
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                if next_line and not next_line.startswith('--'):
                    title = next_line
                    break
                j += 1

            chapters.append({
                'title': title,
                'start_time': start,
                'end_time': end,
            })
            i = j + 1
        else:
            i += 1

    _calculate_end_times(chapters)
    return chapters


def _parse_vtt_time(time_str: str) -> float:
    """Parse VTT timestamp (HH:MM:SS.mmm or MM:SS.mmm)."""
    parts = time_str.split(':')
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return float(parts[0])


# ─── CSV Parser ──────────────────────────────────────────────

def parse_csv_chapters(content: str) -> ChapterList:
    """
    Parse CSV chapter format.
    Columns: title, start_time, [end_time]
    """
    chapters = []
    for line in content.split('\n'):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue

        parts = [p.strip().strip('"') for p in stripped.split(',')]
        if len(parts) >= 2:
            try:
                title = parts[0]
                start = float(parts[1])
                end = float(parts[2]) if len(parts) >= 3 else start

                chapters.append({
                    'title': title,
                    'start_time': start,
                    'end_time': end,
                })
            except (ValueError, IndexError):
                continue

    _calculate_end_times(chapters)
    return chapters


# ─── JSON Parser ─────────────────────────────────────────────

def parse_json_chapters(content: str) -> ChapterList:
    """Parse JSON chapter format (simple list or object with chapters key)."""
    import json
    data = json.loads(content)
    if isinstance(data, list):
        chapters = data
    elif isinstance(data, dict):
        chapters = data.get('chapters', data.get('tracks', []))
    else:
        return []

    result = []
    for ch in chapters:
        if isinstance(ch, dict) and ('title' in ch or 'name' in ch):
            result.append({
                'title': ch.get('title') or ch.get('name', f'Chapter {len(result) + 1}'),
                'start_time': float(ch.get('start_time', ch.get('start', ch.get('time', 0)))),
                'end_time': float(ch.get('end_time', ch.get('end', ch.get('start_time', 0)))),
            })
        elif isinstance(ch, (list, tuple)) and len(ch) >= 2:
            result.append({
                'title': str(ch[0]),
                'start_time': float(ch[1]),
                'end_time': float(ch[2]) if len(ch) > 2 else float(ch[1]),
            })

    _calculate_end_times(result)
    return result


# ═══════════════════════════════════════════════════════════════
# Export Writers
# ═══════════════════════════════════════════════════════════════

def export_chapters(chapters: ChapterList, output_path: str, format: str = 'vtt') -> str:
    """
    Export chapter list to a file.

    Args:
        chapters: List of chapter dicts
        output_path: Output file path
        format: Export format - 'vtt', 'cue', 'audacity', 'csv', 'json', 'chapters.txt'

    Returns:
        Path to written file
    """
    writers = {
        'vtt': _write_vtt,
        'cue': _write_cue,
        'audacity': _write_audacity,
        'csv': _write_csv,
        'json': _write_json,
        'chapters.txt': _write_audacity,
    }

    writer = writers.get(format)
    if not writer:
        raise ValueError(f"Unsupported export format: {format}. Supported: {', '.join(writers)}")

    content = writer(chapters)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)

    return output_path


def _format_ts(seconds: float) -> str:
    """Format seconds to HH:MM:SS.mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f'{h:02d}:{m:02d}:{s:06.3f}'


def _write_vtt(chapters: ChapterList) -> str:
    lines = ['WEBVTT', '']
    for ch in chapters:
        start = _format_ts(ch['start_time'])
        end = _format_ts(ch['end_time'])
        lines.append(f'{start} --> {end}')
        lines.append(ch['title'])
        lines.append('')
    return '\n'.join(lines)


def _write_cue(chapters: ChapterList) -> str:
    lines = ['REM GENERATED BY BPM4B', '']
    for i, ch in enumerate(chapters):
        lines.append(f'  TRACK {i + 1:02d} AUDIO')
        lines.append(f'    TITLE "{ch["title"]}"')
        lines.append(f'    INDEX 01 {_format_cue_time(ch["start_time"])}')
        lines.append('')
    return '\n'.join(lines)


def _format_cue_time(seconds: float) -> str:
    """Format seconds to CUE format (MM:SS:FF)."""
    m = int(seconds // 60)
    s = int(seconds % 60)
    frames = int((seconds - int(seconds)) * 75)
    return f'{m:02d}:{s:02d}:{frames:02d}'


def _write_audacity(chapters: ChapterList) -> str:
    lines = []
    for ch in chapters:
        lines.append(f'{ch["start_time"]:.3f}\t{ch["end_time"]:.3f}\t{ch["title"]}')
    return '\n'.join(lines)


def _write_csv(chapters: ChapterList) -> str:
    import csv
    import io
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['title', 'start_time', 'end_time'])
    for ch in chapters:
        writer.writerow([ch['title'], ch['start_time'], ch['end_time']])
    return buf.getvalue()


def _write_json(chapters: ChapterList) -> str:
    import json
    return json.dumps({'chapters': chapters}, indent=2)


# ═══════════════════════════════════════════════════════════════
# Internal Helpers
# ═══════════════════════════════════════════════════════════════

def _calculate_end_times(chapters: ChapterList) -> None:
    """Fill in end times from the next chapter's start time."""
    for i, ch in enumerate(chapters):
        if not ch.get('end_time') or ch['end_time'] <= ch.get('start_time', 0):
            if i + 1 < len(chapters):
                ch['end_time'] = chapters[i + 1].get('start_time', ch['start_time'] + 60)
            else:
                ch['end_time'] = ch['start_time'] + 60


def get_supported_formats() -> Dict[str, str]:
    """Return dict of supported formats and their descriptions."""
    return {
        '.cue': 'CUE sheet format (CD track format)',
        '.txt': 'Audacity label format',
        '.vtt': 'WebVTT subtitle format',
        '.csv': 'Comma-separated values',
        '.json': 'JSON chapter list',
    }


def detect_format(file_path: str) -> Optional[str]:
    """Detect the chapter format of a file."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext in ('.cue', '.vtt', '.csv', '.json'):
        return ext
    if ext == '.txt':
        return '.txt'
    return None
