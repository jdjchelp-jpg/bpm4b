"""
Core functions shared between the main app and Vercel API.
Ported from Node.js v12 lib/core.js — audio conversion, merging, analysis.
"""

import os
import uuid
import subprocess
import json
import logging
import tempfile
import re

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
            # HH:MM:SS
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
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            first_line = result.stdout.split('\n')[0] if result.stdout else 'ffmpeg found'
            return {'available': True, 'version': first_line}
        return {'available': False, 'error': 'ffmpeg returned non-zero exit code'}
    except FileNotFoundError:
        return {'available': False, 'error': 'ffmpeg not found in PATH'}
    except Exception as e:
        return {'available': False, 'error': str(e)}


def get_audio_duration(audio_path):
    """Get audio duration in seconds using ffprobe or ffmpeg."""
    # Try ffprobe first
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', audio_path],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            if data.get('format', {}).get('duration'):
                return float(data['format']['duration'])
    except Exception:
        pass

    # Fallback: parse ffmpeg stderr
    try:
        result = subprocess.run(
            ['ffmpeg', '-i', audio_path, '-hide_banner'],
            capture_output=True, text=True, timeout=30
        )
        output = result.stdout + result.stderr
        m = re.search(r'Duration:\s*(\d+):(\d+):(\d+)\.(\d+)', output)
        if m:
            h, mn, s, cs = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            return h * 3600 + mn * 60 + s + cs / 100
    except Exception:
        pass

    # Last resort: estimate from WAV header
    try:
        with open(audio_path, 'rb') as f:
            header = f.read(44)
            if header[:4] == b'RIFF' and header[8:12] == b'WAVE':
                sample_rate = int.from_bytes(header[24:28], 'little')
                num_channels = int.from_bytes(header[22:24], 'little')
                bits_per_sample = int.from_bytes(header[34:36], 'little')
                data_size = os.path.getsize(audio_path) - 44
                if sample_rate > 0 and num_channels > 0:
                    return data_size / (sample_rate * num_channels * (bits_per_sample / 8))
    except Exception:
        pass

    return 0


def detect_silence(audio_path, silence_duration=0.5, silence_threshold=-50):
    """Detect silence in audio using ffmpeg's silencedetect filter."""
    cmd = [
        'ffmpeg', '-i', audio_path,
        '-af', f'silencedetect=d={silence_duration}:noise={silence_threshold}dB',
        '-f', 'null', '-'
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        output = result.stdout + result.stderr
        silence_events = []
        for line in output.split('\n'):
            if 'silence_start' in line:
                m = re.search(r'silence_start:\s*([\d.]+)', line)
                if m:
                    silence_events.append({'start': float(m.group(1))})
            elif 'silence_end' in line:
                m = re.search(r'silence_end:\s*([\d.]+)\s*\|\s*silence_duration:\s*([\d.]+)', line)
                if m and silence_events:
                    silence_events[-1]['end'] = float(m.group(1))
                    silence_events[-1]['duration'] = float(m.group(2))
        return silence_events
    except Exception as e:
        logger.error(f"Silence detection failed: {e}")
        return []


def convert_mp3_to_m4b(mp3_path, output_path, chapters=None, quality='64k'):
    """Convert MP3 to M4B with optional chapters using ffmpeg."""
    try:
        cmd = ['ffmpeg', '-y', '-i', mp3_path]

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
            try:
                os.remove(chapter_file)
            except OSError:
                pass

        if result.returncode != 0:
            raise Exception(f"FFmpeg error: {result.stderr}")

        return True

    except Exception as e:
        logger.error(f"Error in convert_mp3_to_m4b: {e}")
        raise


def convert_m4b_to_mp3(m4b_path, output_path, quality='128k'):
    """Convert M4B/M4A to MP3 using ffmpeg."""
    try:
        cmd = ['ffmpeg', '-y', '-i', m4b_path, '-c:a', 'libmp3lame', '-b:a', quality, output_path]
        logger.info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"FFmpeg error: {result.stderr}")
        return True
    except Exception as e:
        logger.error(f"Error in convert_m4b_to_mp3: {e}")
        raise


def convert_audio_format(input_path, output_path, target_format='mp3', quality='192k'):
    """
    Convert audio between formats: MP3, WAV, FLAC, AAC, OGG, ALAC.
    Ported from Node.js convertToM4b logic.
    """
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

    cmd = ['ffmpeg', '-y', '-i', input_path, '-c:a', fmt['codec']]

    if target_format.lower() != 'wav' and target_format.lower() != 'flac':
        cmd.extend(['-b:a', quality])

    if target_format.lower() == 'alac':
        # ALAC requires MP4/M4A container
        cmd.extend(['-movflags', '+faststart'])

    cmd.append(output_path)

    logger.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Format conversion error: {result.stderr}")
    return output_path


def audio_glue(input_paths, output_path, normalize=False, volume=1.0):
    """
    Merge multiple audio files into one using ffmpeg concat.
    Ported from Node.js audioGlue.
    """
    if not input_paths:
        raise ValueError("No input files provided")

    work_dir = tempfile.mkdtemp(prefix='bpm4b_glue_')
    normalized_paths = []

    try:
        if normalize:
            for i, path in enumerate(input_paths):
                norm_path = os.path.join(work_dir, f'norm_{i}.wav')
                cmd = ['ffmpeg', '-y', '-i', path, '-af', 'loudnorm=I=-16:LRA=11:TP=-1.5',
                       '-c:a', 'pcm_s16le', norm_path]
                subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                normalized_paths.append(norm_path)
        else:
            normalized_paths = list(input_paths)

        list_file = os.path.join(work_dir, 'concat_list.txt')
        with open(list_file, 'w', encoding='utf-8') as f:
            for p in normalized_paths:
                escaped = p.replace('\\', '/').replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', list_file]

        if volume != 1.0:
            cmd.extend(['-af', f'volume={volume}'])

        cmd.extend(['-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart'])
        cmd.append(output_path)

        logger.info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Audio merge error: {result.stderr}")

        return output_path

    finally:
        # Clean up normalized temp files (only those created inside work_dir)
        for p in normalized_paths:
            if p.startswith(work_dir):
                try:
                    os.remove(p)
                except OSError:
                    pass
        try:
            os.remove(list_file)
        except (OSError, NameError):
            pass
        try:
            os.rmdir(work_dir)
        except OSError:
            pass


def folder_to_m4b(folder_path, output_path, options=None):
    """
    Convert a folder of audio files into a single M4B with chapter markers.
    Ported from Node.js folderToM4b.
    """
    options = options or {}
    concurrency = options.get('concurrency', 4)
    fast_mode = options.get('fastMode', False)
    audio_quality = options.get('audio_quality', '128k')
    metadata = options.get('metadata', {})

    audio_extensions = {'.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.wma', '.opus'}
    files = sorted([
        os.path.join(folder_path, f)
        for f in os.listdir(folder_path)
        if os.path.splitext(f)[1].lower() in audio_extensions
    ], key=lambda x: os.path.basename(x).lower())

    if not files:
        raise ValueError(f"No audio files found in {folder_path}")

    work_dir = tempfile.mkdtemp(prefix='bpm4b_folder_')
    wav_files = []

    try:
        for i, file_path in enumerate(files):
            wav_path = os.path.join(work_dir, f'file_{i:04d}.wav')
            cmd = ['ffmpeg', '-y', '-i', file_path, '-c:a', 'pcm_s16le', wav_path]
            subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            wav_files.append((wav_path, os.path.basename(file_path)))

        # Build chapter metadata from filenames
        chapters = []
        for i, (wav_path, filename) in enumerate(wav_files):
            duration = get_audio_duration(wav_path)
            title = os.path.splitext(filename)[0]
            # Clean up common chapter naming
            title = re.sub(r'^\d+[\s\-_\.]+', '', title)
            title = re.sub(r'[_\s]+', ' ', title).strip()
            chapters.append({'title': title, 'start_time': 0})

        # Calculate cumulative start times
        cumulative = 0
        for ch in chapters:
            ch['start_time'] = cumulative
            ch_idx = chapters.index(ch)
            duration = get_audio_duration(wav_files[ch_idx][0])
            ch['end_time'] = cumulative + duration
            cumulative += duration

        # Concatenate all WAVs
        concat_list = os.path.join(work_dir, 'concat.txt')
        with open(concat_list, 'w', encoding='utf-8') as f:
            for wav_path, _ in wav_files:
                escaped = wav_path.replace('\\', '/').replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        combined_wav = os.path.join(work_dir, 'combined.wav')
        cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_list,
               '-c:a', 'pcm_s16le', combined_wav]
        subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        # Convert to M4B with chapters
        convert_mp3_to_m4b(combined_wav, output_path, chapters, quality=audio_quality)

        return {
            'output_path': output_path,
            'chapters': chapters,
            'total_duration': cumulative,
            'files_processed': len(files),
        }

    finally:
        import shutil
        shutil.rmtree(work_dir, ignore_errors=True)


def _concat_wavs_ffmpeg(wav_paths, output_path):
    """Concatenate WAV files using ffmpeg concat demuxer."""
    list_file = output_path + '.list.txt'
    try:
        with open(list_file, 'w', encoding='utf-8') as f:
            for p in wav_paths:
                escaped = p.replace('\\', '/').replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")
        cmd = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', list_file, '-c', 'copy', output_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed: {result.stderr}")
    finally:
        try:
            os.remove(list_file)
        except OSError:
            pass
