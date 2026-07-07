"""
Audiobook Builder Module
Orchestrates the full document-to-audiobook pipeline:
  1. Parse document → 2. Detect chapters → 3. Generate TTS audio → 4. Assemble M4B
Ported from Node.js audiobook-builder.js
"""

import os
import uuid
import tempfile
import logging
import shutil

logger = logging.getLogger(__name__)


def build_audiobook(input_path, output_path, options=None):
    """
    Build an audiobook from a document file.

    Args:
        input_path: Path to source document (PDF/DOCX/TXT/EPUB)
        output_path: Path for output M4B file
        options: dict with optional keys:
            voice (str): Kokoro voice, default 'af_heart'
            speed (float): Speech speed, default 1.0
            audio_quality (str): M4B bitrate, default '64k'
            on_progress (callable): progress(percent_or_stage, detail)
            custom_chapters (list): Override detected chapters

    Returns:
        dict: {output_path, chapters, total_duration}
    """
    from .document_parser import parse_document
    from .chapter_detector import detect_chapters
    from .tts import generate_tts, get_audio_duration
    from .core import convert_mp3_to_m4b

    options = options or {}
    voice = options.get('voice', 'af_heart')
    speed = options.get('speed', 1.0)
    audio_quality = options.get('audio_quality', '64k')
    on_progress = options.get('on_progress')
    custom_chapters = options.get('custom_chapters')

    work_dir = tempfile.mkdtemp(prefix='bpm4b_audiobook_')

    def progress(stage, detail=''):
        if on_progress:
            on_progress(stage, detail)

    try:
        # Stage 1: Parse document (5%)
        progress(5, 'Extracting text from document...')
        doc = parse_document(input_path)
        text = doc.get('text', '')
        headings = doc.get('headings', [])

        if not text or not text.strip():
            raise ValueError('No text content could be extracted from the document')

        # Stage 2: Detect chapters (10%)
        progress(10, 'Detecting chapter boundaries...')
        chapters = detect_chapters(text, headings)

        if custom_chapters:
            mapped = []
            for custom in custom_chapters:
                orig_idx = custom.get('original_index')
                orig = chapters[orig_idx] if orig_idx is not None and orig_idx < len(chapters) else None
                if not orig:
                    orig = next((c for c in chapters if c['title'] == custom.get('title')), None) or chapters[0]
                if orig:
                    mapped.append({**orig, 'title': custom.get('title') or orig['title'],
                                   'number': custom.get('number') or orig.get('number')})
            if mapped:
                chapters = mapped

        progress(15, f"Found {len(chapters)} chapter(s). Initializing TTS...")

        # Stage 3: Generate TTS for each chapter (15%-85%)
        chapter_audio_results = []
        total_chapters = len(chapters)

        for i, chapter in enumerate(chapters):
            sub_pct = 15 + round((i / total_chapters) * 70)
            progress(sub_pct, f"Generating audio: {chapter['title']} ({i + 1}/{total_chapters})")

            chunk_path = os.path.join(work_dir, f'chapter_{i}_{uuid.uuid4().hex[:8]}.wav')
            generate_tts(chapter['content'], chunk_path, voice=voice, speed=speed)
            duration = get_audio_duration(chunk_path)

            chapter_audio_results.append({
                'chapter_title': chapter['title'],
                'audio_path': chunk_path,
                'duration_seconds': duration,
            })

        # Stage 4: Concatenate all chapter audio (90%)
        progress(90, 'Combining chapter audio...')
        all_paths = [r['audio_path'] for r in chapter_audio_results]
        combined_wav = os.path.join(work_dir, 'combined.wav')

        if len(all_paths) == 1:
            shutil.copy(all_paths[0], combined_wav)
        else:
            _concatenate_wavs_ffmpeg(all_paths, combined_wav)

        # Stage 5: Build chapter metadata
        cumulative = 0.0
        chapter_metadata = []
        for r in chapter_audio_results:
            chapter_metadata.append({
                'title': r['chapter_title'],
                'start_time': cumulative,
                'end_time': cumulative + r['duration_seconds'],
            })
            cumulative += r['duration_seconds']

        # Stage 6: Convert to M4B (95-100%)
        progress(95, 'Creating final M4B with embedded chapters...')
        convert_mp3_to_m4b(combined_wav, output_path, chapter_metadata, quality=audio_quality)

        progress(100, 'Audiobook generation complete!')

        return {
            'output_path': output_path,
            'chapters': chapter_metadata,
            'total_duration': cumulative,
        }

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def preview_chapters(input_path):
    """
    Preview chapter detection without generating audio.
    Returns chapter list with word counts and estimated duration.
    """
    from .document_parser import parse_document
    from .chapter_detector import detect_chapters

    doc = parse_document(input_path)
    text = doc.get('text', '')
    if not text or not text.strip():
        raise ValueError('No text content could be extracted from the document')

    chapters = detect_chapters(text, doc.get('headings', []))
    total_chars = sum(len(c['content']) for c in chapters)

    # ~750 chars/minute at normal speaking pace
    est_minutes = max(1, total_chars // 750)
    hours, mins = divmod(est_minutes, 60)
    estimated_duration = f"{hours}h {mins}m" if hours else f"{mins}m"

    gen_gpu = max(1, total_chars // 600)
    gen_cpu = max(1, total_chars // 60)

    def fmt_time(s):
        if s < 60:
            return f"{s}s"
        m, sec = divmod(s, 60)
        return f"{m}m {sec}s" if sec else f"{m}m"

    return {
        'chapters': [
            {
                'number': c.get('number') or i + 1,
                'title': c['title'],
                'content_length': len(c['content']),
                'word_count': len(c['content'].split()),
                'preview': c['content'][:200] + ('...' if len(c['content']) > 200 else ''),
            }
            for i, c in enumerate(chapters)
        ],
        'total_characters': total_chars,
        'estimated_duration': estimated_duration,
        'generation_time_estimate': {
            'gpu': fmt_time(gen_gpu),
            'cpu': fmt_time(gen_cpu),
        },
    }


def _concatenate_wavs_ffmpeg(wav_paths, output_path):
    import subprocess
    list_file = output_path + '.list.txt'
    try:
        with open(list_file, 'w', encoding='utf-8') as f:
            for p in wav_paths:
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
