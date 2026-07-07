"""
TTS Engine Module
Generates speech audio from text using Kokoro ONNX (local, no API key needed).
Falls back gracefully if kokoro is unavailable.

Uses kokoro-onnx (pip install kokoro-onnx) — the PyPI-friendly variant.
The original `kokoro` package requires a specific install path; kokoro-onnx
works out of the box with just pip.
"""

import os
import re
import uuid
import logging
import tempfile
import subprocess

logger = logging.getLogger(__name__)

MAX_CHUNK_LENGTH = 1000

# Lazy-loaded pipeline
_pipeline = None
_pipeline_lang = None


def _get_pipeline(lang_code='a'):
    """Lazy-load Kokoro pipeline. Tries kokoro first, then kokoro-onnx."""
    global _pipeline, _pipeline_lang
    if _pipeline is not None and _pipeline_lang == lang_code:
        return _pipeline

    # Try the standard kokoro package (KPipeline API)
    try:
        from kokoro import KPipeline
        logger.info("Initializing Kokoro TTS Pipeline (kokoro)...")
        _pipeline = KPipeline(lang_code=lang_code)
        _pipeline_lang = lang_code
        return _pipeline
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"kokoro KPipeline init failed: {e}")

    # Try kokoro-onnx
    try:
        from kokoro_onnx import Kokoro
        logger.info("Initializing Kokoro ONNX...")
        _pipeline = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")
        _pipeline_lang = lang_code
        return _pipeline
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"kokoro-onnx init failed: {e}")

    raise RuntimeError(
        "No TTS engine found. Install one:\n"
        "  pip install kokoro>=0.9.4 soundfile\n"
        "  OR pip install kokoro-onnx soundfile"
    )


def split_text_into_chunks(text, max_length=MAX_CHUNK_LENGTH):
    """Split text into chunks at sentence boundaries."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        search = remaining[:max_length]
        split_idx = -1

        # Prefer sentence boundaries
        for end in ['. ', '! ', '? ', '.\n', '!\n', '?\n']:
            idx = search.rfind(end)
            if idx > split_idx:
                split_idx = idx + len(end)

        if split_idx <= 0:
            idx = search.rfind('\n\n')
            if idx > 0:
                split_idx = idx + 2

        if split_idx <= 0:
            idx = search.rfind('\n')
            if idx > 0:
                split_idx = idx + 1

        if split_idx <= 0:
            idx = search.rfind(' ')
            if idx > 0:
                split_idx = idx + 1

        if split_idx <= 0:
            split_idx = max_length

        chunk = remaining[:split_idx].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_idx:].strip()

    return [c for c in chunks if c]


def _generate_chunk_kokoro(pipeline, text, voice, speed):
    """Generate WAV bytes for a text chunk using standard kokoro KPipeline."""
    import numpy as np
    try:
        import soundfile as sf
        import io
        all_audio = []
        for _, _, audio in pipeline(text, voice=voice, speed=speed, split_pattern=r'\n+'):
            all_audio.append(audio)
        if not all_audio:
            raise RuntimeError("No audio generated")
        combined = np.concatenate(all_audio)
        buf = io.BytesIO()
        sf.write(buf, combined, 24000, format='WAV')
        return buf.getvalue()
    except ImportError:
        raise ImportError("soundfile is required: pip install soundfile")


def _generate_chunk_kokoro_onnx(pipeline, text, voice, speed):
    """Generate WAV bytes using kokoro-onnx."""
    import numpy as np
    import io
    samples, sample_rate = pipeline.create(text, voice=voice, speed=speed, lang='en-us')
    try:
        import soundfile as sf
        buf = io.BytesIO()
        sf.write(buf, samples, sample_rate, format='WAV')
        return buf.getvalue()
    except ImportError:
        # Manual WAV header
        return _make_wav(samples, sample_rate)


def _make_wav(audio_array, sample_rate):
    """Wrap float32 audio in a WAV container without soundfile."""
    import struct
    import numpy as np
    pcm = (np.clip(audio_array, -1, 1) * 32767).astype('<i2').tobytes()
    data_size = len(pcm)
    header = struct.pack('<4sI4s4sIHHIIHH4sI',
                         b'RIFF', 36 + data_size, b'WAVE',
                         b'fmt ', 16, 1, 1,
                         sample_rate, sample_rate * 2, 2, 16,
                         b'data', data_size)
    return header + pcm


def generate_tts(text, output_path, voice='af_heart', speed=1.0, lang_code='a'):
    """
    Generate audio from text using Kokoro and save as WAV.

    Args:
        text: Input text
        output_path: Output WAV file path
        voice: Kokoro voice ID (e.g., 'af_heart', 'af_sky')
        speed: Speech speed multiplier
        lang_code: Language code for pipeline ('a'=US English, 'b'=British)
    """
    pipeline = _get_pipeline(lang_code)
    chunks = split_text_into_chunks(text)
    chunk_wavs = []

    tmp_dir = tempfile.mkdtemp()
    try:
        for i, chunk in enumerate(chunks):
            chunk_path = os.path.join(tmp_dir, f'chunk_{i}.wav')
            # Detect which API we got
            if hasattr(pipeline, '__call__') and hasattr(pipeline, 'lang_code'):
                # KPipeline style
                wav_bytes = _generate_chunk_kokoro(pipeline, chunk, voice, speed)
            else:
                # kokoro-onnx style
                wav_bytes = _generate_chunk_kokoro_onnx(pipeline, chunk, voice, speed)

            with open(chunk_path, 'wb') as f:
                f.write(wav_bytes)
            chunk_wavs.append(chunk_path)

        if len(chunk_wavs) == 1:
            import shutil
            shutil.move(chunk_wavs[0], output_path)
        else:
            _concatenate_wavs(chunk_wavs, output_path)
    finally:
        for p in chunk_wavs:
            try:
                os.remove(p)
            except OSError:
                pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass

    return True


def _concatenate_wavs(wav_paths, output_path):
    """Concatenate WAV files using ffmpeg."""
    import tempfile
    list_file = output_path + '.list.txt'
    try:
        with open(list_file, 'w', encoding='utf-8') as f:
            for p in wav_paths:
                # ponytail: forward slashes work on all platforms with ffmpeg concat
                escaped = p.replace('\\', '/').replace("'", "\\'")
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


def get_audio_duration(audio_path):
    """Get audio duration in seconds using ffmpeg."""
    cmd = ['ffmpeg', '-i', audio_path, '-hide_banner']
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout + result.stderr
    m = re.search(r'Duration:\s*(\d+):(\d+):(\d+)\.(\d+)', output)
    if m:
        h, mn, s, cs = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        return h * 3600 + mn * 60 + s + cs / 100
    return 0


# Voices list mirrored from Node.js tts-engine.js
AVAILABLE_VOICES = [
    {'id': 'af_heart', 'name': 'Heart (F)', 'lang': '🇺🇸'},
    {'id': 'af_sky', 'name': 'Sky (F)', 'lang': '🇺🇸'},
    {'id': 'af_bella', 'name': 'Bella (F)', 'lang': '🇺🇸'},
    {'id': 'af_nicole', 'name': 'Nicole (F)', 'lang': '🇺🇸'},
    {'id': 'af_sarah', 'name': 'Sarah (F)', 'lang': '🇺🇸'},
    {'id': 'am_adam', 'name': 'Adam (M)', 'lang': '🇺🇸'},
    {'id': 'am_michael', 'name': 'Michael (M)', 'lang': '🇺🇸'},
    {'id': 'bf_emma', 'name': 'Emma (F)', 'lang': '🇬🇧'},
    {'id': 'bf_isabella', 'name': 'Isabella (F)', 'lang': '🇬🇧'},
    {'id': 'bm_george', 'name': 'George (M)', 'lang': '🇬🇧'},
    {'id': 'bm_lewis', 'name': 'Lewis (M)', 'lang': '🇬🇧'},
]
