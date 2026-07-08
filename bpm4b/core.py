"""
Core functions shared between the main app and Vercel API.
Enhanced in v13 to delegate to new specialized modules.
"""

import os
import uuid
import subprocess
import json
import logging
import tempfile
import re
import shutil

from .ffmpeg_utils import find_ffmpeg, find_ffprobe, get_audio_duration as ffmpeg_get_duration
from .path_utils import safe_path, ensure_dir, cleanup_file, ffmpeg_concat_entry, temp_dir, cleanup_dir
from .concurrency_guard import auto_concurrency
from .splicer import splice_audio_files
from .cover_art import inject_cover_art, extract_cover_art, inherit_metadata_from_first_file
from .text_processor import normalize_chapter_title, normalize_all_chapter_titles, resolve_roman_numerals_in_text

logger = logging.getLogger(__name__)


def parse_time_to_seconds(time_input):
    """
    Parse time input to seconds.

    Supports:
    - Integer/float seconds (e.g., 390, 390.5)
    - MM:SS format (e.g., "6:30" -> 390)
    - MM:SS.sss format (e.g., "6:30.5" -> 390.5)
    - HH:MM:SS format (e.g., "1:00:00" -> 3600)

    Returns:
        float: Time in seconds

    Raises:
        ValueError: If the format is invalid
    """
    if isinstance(time_input, (int, float)):
        return float(time_input)

    if isinstance(time_input, str):
        try:
            return float(time_input)
        except ValueError:
            pass

        parts = time_input.strip().split(':')
        if len(parts) == 3:
            try:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            except ValueError:
                pass
        elif len(parts) == 2:
            try:
                return float(parts[0]) * 60 + float(parts[1])
            except ValueError:
                pass

    raise ValueError(f"Invalid time format: {time_input}. Use seconds, MM:SS, or HH:MM:SS")


def check_ffmpeg():
    """Check if ffmpeg is available and return version info."""
    from .ffmpeg_utils import get_ffmpeg_info
    return get_ffmpeg_info()


def get_audio_duration(audio_path):
    """Get audio duration in seconds using ffprobe or ffmpeg."""
    return ffmpeg_get_duration(audio_path)


def detect_silence(audio_path, silence_duration=0.5, silence_threshold=-50):
    """Detect silence in audio using ffmpeg's silencedetect filter."""
    from .ffmpeg_utils import detect_silence_regions
    events = detect_silence_regions(
        audio_path,
        noise_threshold=f'{silence_threshold}dB',
        min_silence_duration=silence_duration
    )
    return events


def convert_mp3_to_m4b(mp3_path, output_path, chapters=None, quality='64k'):
    """Convert MP3 to M4B with optional chapters using ffmpeg."""
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")

    try:
        cmd = [ffmpeg, '-y', '-i', mp3_path]

        chapter_file = None
        if chapters:
            chapter_file = os.path.join(os.path.dirname(output_path), f'chapters_{uuid.uuid4().hex[:8]}.txt')
            with open(chapter_file, 'w', encoding='utf-8') as f:
                f.write(';FFMETADATA1\n')
                for i, chapter in enumerate(chapters):
                    start_time = parse_time_to_seconds(chapter['start_time'])
                    if 'end_time' in chapter and chapter['end_time']:
                        end_time = parse_time_to_seconds(chapter['end_time'])
                    elif i < len(chapters) - 1:
                        end_time = parse_time_to_seconds(chapters[i+1]['start_time'])
                    else:
                        end_time = 999999

                    f.write(f'[CHAPTER]\n')
                    f.write(f'TIMEBASE=1/1000\n')
                    f.write(f'START={int(start_time * 1000)}\n')
                    f.write(f'END={int(end_time * 1000)}\n')
                    f.write(f'title={chapter["title"]}\n\n')

            cmd.extend(['-i', chapter_file, '-map_metadata', '1'])

        cmd.extend(['-c:a', 'aac', '-b:a', quality])
        cmd.append(output_path)

        logger.info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if chapter_file and os.path.exists(chapter_file):
            cleanup_file(chapter_file)

        if result.returncode != 0:
            raise Exception(f"FFmpeg error: {result.stderr}")

        return True

    except Exception as e:
        logger.error(f"Error in convert_mp3_to_m4b: {e}")
        raise


def convert_m4b_to_mp3(m4b_path, output_path, quality='128k'):
    """Convert M4B/M4A to MP3 using ffmpeg."""
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")
    try:
        cmd = [ffmpeg, '-y', '-i', m4b_path, '-c:a', 'libmp3lame', '-b:a', quality, output_path]
        logger.info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"FFmpeg error: {result.stderr}")
        return True
    except Exception as e:
        logger.error(f"Error in convert_m4b_to_mp3: {e}")
        raise


def convert_audio_format(input_path, output_path, target_format='mp3', quality='192k'):
    """Convert audio between formats: MP3, WAV, FLAC, AAC, OGG, ALAC."""
    format_map = {
        'mp3': {'codec': 'libmp3lame', 'ext': '.mp3'},
        'wav': {'codec': 'pcm_s16le', 'ext': '.wav'},
        'flac': {'codec': 'flac', 'ext': '.flac'},
        'aac': {'codec': 'aac', 'ext': '.aac'},
        'ogg': {'codec': 'libvorbis', 'ext': '.ogg'},
        'alac': {'codec': 'alac', 'ext': '.m4a'},
    }

    fmt = format_map.get(target_format.lower())
    if not fmt:
        raise ValueError(f"Unsupported target format: {target_format}. Supported: {', '.join(format_map)}")

    ext = os.path.splitext(output_path)[1].lower()
    if not ext or ext != fmt['ext']:
        output_path = os.path.splitext(output_path)[0] + fmt['ext']

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")
    cmd = [ffmpeg, '-y', '-i', input_path, '-c:a', fmt['codec']]

    if target_format.lower() not in ('wav', 'flac'):
        cmd.extend(['-b:a', quality])

    if target_format.lower() == 'alac':
        cmd.extend(['-movflags', '+faststart'])

    cmd.append(output_path)
    logger.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Format conversion error: {result.stderr}")
    return output_path


def audio_glue(input_paths, output_path, normalize=False, volume=1.0):
    """Merge multiple audio files into one using ffmpeg concat."""
    if not input_paths:
        raise ValueError("No input files provided")

    # Delegate to the new splicer module for zero-copy merging
    return splice_audio_files(
        input_paths, output_path,
        stream_copy=not normalize,  # Stream copy unless normalizing
        normalize=normalize,
        volume=volume,
        audio_quality='128k',
    )


def folder_to_m4b(folder_path, output_path, options=None):
    """Convert a folder of audio files into a single M4B with chapter markers."""
    from .ffmpeg_utils import get_audio_duration as get_dur
    from .concurrency_guard import recommend_concurrency
    from .cache_manager import get_cache

    options = options or {}
    audio_quality = options.get('audio_quality', '128k')
    use_cache = options.get('cache_enabled', False)
    metadata = options.get('metadata', {})

    audio_extensions = {'.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.wma', '.opus'}
    files = sorted([
        os.path.join(folder_path, f)
        for f in os.listdir(folder_path)
        if os.path.splitext(f)[1].lower() in audio_extensions
    ], key=lambda x: os.path.basename(x).lower())

    if not files:
        raise ValueError(f"No audio files found in {folder_path}")

    concurrency = recommend_concurrency('wav_encode')
    work_dir = temp_dir('bpm4b_folder_')
    wav_files = []

    try:
        for i, file_path in enumerate(files):
            wav_path = os.path.join(work_dir, f'file_{i:04d}.wav')

            if use_cache:
                from .cache_manager import get_cached_or_process
                def to_wav(src, out):
                    ffmpeg = find_ffmpeg()
                    subprocess.run([ffmpeg, '-y', '-i', src, '-c:a', 'pcm_s16le', out],
                                   capture_output=True, text=True, timeout=300)
                    return out
                get_cached_or_process(file_path, to_wav, wav_path, '.wav', force_reprocess=not use_cache)
            else:
                ffmpeg = find_ffmpeg()
                cmd = [ffmpeg, '-y', '-i', file_path, '-c:a', 'pcm_s16le', wav_path]
                subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            wav_files.append((wav_path, os.path.basename(file_path)))

        # Build chapter metadata from filenames with normalization
        from .text_processor import normalize_chapter_filename
        chapters = []
        for i, (wav_path, filename) in enumerate(wav_files):
            duration = get_dur(wav_path)
            parsed = normalize_chapter_filename(filename)
            if parsed:
                title = parsed['title']
            else:
                title = os.path.splitext(filename)[0]
                title = re.sub(r'^\d+[\s\-_\.]+', '', title)
                title = re.sub(r'[_]+', ' ', title).strip()
            chapters.append({'title': title, 'start_time': 0, 'end_time': duration})

        # Calculate cumulative start times
        cumulative = 0
        for ch in chapters:
            ch['start_time'] = cumulative
            cumulative += ch['end_time']
            ch['end_time'] = cumulative

        # Build concat list
        concat_list = os.path.join(work_dir, 'concat.txt')
        with open(concat_list, 'w', encoding='utf-8') as f:
            for wav_path, _ in wav_files:
                f.write(ffmpeg_concat_entry(wav_path) + '\n')

        combined_wav = os.path.join(work_dir, 'combined.wav')
        ffmpeg = find_ffmpeg()
        cmd = [ffmpeg, '-y', '-f', 'concat', '-safe', '0', '-i', concat_list,
               '-c:a', 'pcm_s16le', combined_wav]
        subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        # Apply metadata inheritance from first file
        if not metadata.get('title') and not metadata.get('author'):
            inherited = inherit_metadata_from_first_file(files)
            metadata = {**inherited, **metadata}

        # Convert to M4B with chapters
        convert_mp3_to_m4b(combined_wav, output_path, chapters, quality=audio_quality)

        # Apply cover art if inherited
        if metadata:
            from .cover_art import inject_cover_art
            try:
                cover_data = extract_cover_art(files[0])
                if cover_data:
                    tmp_cover = os.path.join(work_dir, 'cover.jpg')
                    with open(tmp_cover, 'wb') as f:
                        f.write(cover_data)
                    inject_cover_art(output_path, tmp_cover, output_path + '.tmp')
                    if os.path.exists(output_path + '.tmp'):
                        shutil.move(output_path + '.tmp', output_path)
            except Exception:
                pass

        return {
            'output_path': output_path,
            'chapters': chapters,
            'total_duration': cumulative,
            'files_processed': len(files),
        }

    finally:
        cleanup_dir(work_dir)


def _concat_wavs_ffmpeg(wav_paths, output_path):
    """Concatenate WAV files using ffmpeg concat demuxer."""
    list_file = output_path + '.list.txt'
    try:
        with open(list_file, 'w', encoding='utf-8') as f:
            for p in wav_paths:
                escaped = p.replace('\\', '/').replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")
        ffmpeg = find_ffmpeg()
        cmd = [ffmpeg, '-y', '-f', 'concat', '-safe', '0', '-i', list_file, '-c', 'copy', output_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed: {result.stderr}")
    finally:
        cleanup_file(list_file)
