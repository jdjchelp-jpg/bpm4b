"""
Abogen Integration Module

Replaces the built-in audiobook generation pipeline with integration
to the abogen TTS engine (denizsafak/abogen). BPM4B handles pre-processing
(chapter detection, Roman numeral resolution, stat block compaction)
before passing to abogen for TTS audio generation.

Feature #1 from the BPM4B v13 feature set.
"""

import os
import sys
import json
import uuid
import logging
import subprocess
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path

from .path_utils import temp_dir, cleanup_dir, ensure_dir, safe_path
from .text_processor import (
    resolve_roman_numerals_in_text,
    normalize_all_chapter_titles,
    compact_stat_blocks,
    detect_stat_blocks,
)
from .chapter_detector import detect_chapters
from .document_parser import parse_document

logger = logging.getLogger(__name__)

# ─── Abogen Discovery ───────────────────────────────────────

def find_abogen() -> Optional[str]:
    """Find the abogen executable in PATH."""
    import shutil
    # Check for abogen and abogen-web
    for name in ['abogen', 'abogen-web']:
        path = shutil.which(name)
        if path:
            return path
    return None


def is_abogen_available() -> bool:
    """Check if abogen is installed and available."""
    return find_abogen() is not None


# ─── BPM4B Pre-Processing Pipeline ──────────────────────────

def preprocess_for_abogen(
    input_path: str,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run the BPM4B pre-processing pipeline on a document before passing to abogen.

    Steps:
      1. Parse document (PDF, DOCX, EPUB, TXT, MD)
      2. Detect chapters with Roman numeral resolution
      3. Optionally compact LitRPG stat blocks
      4. Normalize chapter titles
      5. Generate cleaned text and chapter manifest

    Args:
        input_path: Path to source document
        options: dict with keys:
            resolve_roman (bool): Convert Roman numerals (default: True)
            stat_block_mode (str): 'summarize', 'skip', 'keep', 'flag' (default: 'summarize')
            mode (str): 'ordinal' or 'cardinal' for Roman numeral output

    Returns:
        dict with preprocessed data for abogen input
    """
    if options is None:
        options = {}

    resolve_roman = options.get('resolve_roman', True)
    stat_block_mode = options.get('stat_block_mode', 'summarize')
    mode = options.get('mode', 'ordinal')

    # Step 1: Parse document
    doc = parse_document(input_path)
    text = doc.get('text', '')
    headings = doc.get('headings', [])

    if not text or not text.strip():
        raise ValueError('No text content could be extracted from the document')

    # Step 2: Roman numeral resolution in full text
    if resolve_roman:
        text = resolve_roman_numerals_in_text(text, mode=mode)

    # Step 3: LitRPG stat block compaction
    if stat_block_mode != 'keep':
        text = compact_stat_blocks(text, mode=stat_block_mode)

    # Step 4: Detect and normalize chapters
    chapters = detect_chapters(text, headings)

    if resolve_roman:
        chapters = normalize_all_chapter_titles(chapters)

    # Step 5: Build cleaned text with chapter markers
    cleaned_text = _build_chaptered_text(chapters)

    return {
        'document_path': input_path,
        'full_text': cleaned_text,
        'chapters': chapters,
        'chapter_count': len(chapters),
        'total_chars': len(cleaned_text),
        'preprocessing_options': options,
        'stat_blocks_found': len(detect_stat_blocks(text)) if stat_block_mode != 'keep' else 0,
    }


def _build_chaptered_text(chapters: List[Dict]) -> str:
    """Rebuild text with chapter markers for TTS."""
    parts = []
    for i, ch in enumerate(chapters):
        parts.append(f"[CHAPTER {ch.get('number', i + 1)}]")
        parts.append(ch.get('title', f'Chapter {i + 1}'))
        parts.append('')
        parts.append(ch.get('content', ''))
        parts.append('')
    return '\n'.join(parts)


# ─── Abogen Execution ───────────────────────────────────────

def run_abogen(
    input_path: str,
    output_path: str,
    options: Optional[Dict[str, Any]] = None,
    on_progress: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    Run abogen on a pre-processed document.

    BPM4B handles pre-processing (chapter detection, Roman numeral resolution,
    stat block compaction), then delegates TTS audio generation to abogen.

    Args:
        input_path: Path to pre-processed document or raw document
        output_path: Output M4B path
        options: Abogen options dict with keys:
            voice (str): Kokoro voice
            speed (float): Speech speed
            format (str): Output format
            abogen_path (str): Custom path to abogen binary
            preprocess (bool): Run BPM4B pre-processing first (default: True)

    Returns:
        dict with results
    """
    if options is None:
        options = {}

    abogen_path = options.get('abogen_path') or find_abogen()
    if not abogen_path:
        raise RuntimeError(
            "abogen not found. Install it:\n"
            "  pip install abogen\n"
            "  OR visit: https://github.com/denizsafak/abogen"
        )

    voice = options.get('voice', 'af_heart')
    speed = options.get('speed', 1.0)
    output_format = options.get('format', 'm4b')
    do_preprocess = options.get('preprocess', True)

    work_dir = temp_dir('bpm4b_abogen_')

    try:
        # Pre-processing
        preprocessed_input = input_path
        if do_preprocess:
            if on_progress:
                on_progress('preprocess', 'Running BPM4B preprocessing...')

            preprocessed = preprocess_for_abogen(input_path, options)

            # Write preprocessed text to a temp file for abogen
            preprocessed_input = os.path.join(work_dir, 'preprocessed.txt')
            with open(preprocessed_input, 'w', encoding='utf-8') as f:
                f.write(preprocessed['full_text'])

            if on_progress:
                on_progress('preprocess_complete',
                            f"Preprocessed: {preprocessed['chapter_count']} chapters, "
                            f"{preprocessed['total_chars']:,} chars, "
                            f"{preprocessed.get('stat_blocks_found', 0)} stat blocks found")

        # Run abogen
        if on_progress:
            on_progress('abogen', 'Starting abogen TTS generation...')

        cmd = [
            abogen_path,
            preprocessed_input,
            '-o', output_path,
            '--voice', voice,
            '--speed', str(speed),
            '--format', output_format,
        ]

        logger.info(f"Running abogen: {' '.join(cmd)}")
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=3600
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or 'Unknown error'
            raise RuntimeError(f"abogen failed: {error_msg[:500]}")

        if on_progress:
            on_progress('complete', 'Abogen generation complete!')

        return {
            'output_path': output_path,
            'input_used': preprocessed_input,
            'abogen_command': ' '.join(cmd),
            'abogen_output': result.stdout[-500:] if result.stdout else '',
        }

    finally:
        cleanup_dir(work_dir)


# ─── BookMagic Pre-Processing (for user-provided files) ─────

def bpm4b_magic(
    input_path: str,
    output_path: str,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    BPM4B Magic: Apply all preprocessing enhancements to a file.

    This is the main entry point users call to "magically improve" files
    before passing to abogen. Handles:
      - Roman numeral chapter detection & resolution
      - Chapter title normalization (Chapter IV → Chapter 4)
      - LitRPG stat block compaction
      - Clean text extraction from any document format
      - Metadata enhancement

    Args:
        input_path: Source document path
        output_path: Where to save the enhanced/preprocessed output
        options: Processing options

    Returns:
        dict with processing results
    """
    if options is None:
        options = {}

    result = preprocess_for_abogen(input_path, options)

    # Save the enhanced version
    ext = os.path.splitext(output_path)[1].lower()
    if ext == '.json':
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                'chapters': result['chapters'],
                'chapter_count': result['chapter_count'],
                'total_chars': result['total_chars'],
                'stat_blocks_found': result.get('stat_blocks_found', 0),
                'preprocessing_options': result['preprocessing_options'],
            }, f, indent=2)
    else:
        # Save as cleaned text file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result['full_text'])

    return result
