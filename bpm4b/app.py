import os
import uuid
import json
import logging
import time
import tempfile as tf
import shutil
from flask import Flask, request, send_file, jsonify, render_template
from .core import (
    convert_mp3_to_m4b, convert_m4b_to_mp3, parse_time_to_seconds,
    convert_audio_format, audio_glue, folder_to_m4b, get_audio_duration,
    check_ffmpeg
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__,
            template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
            static_folder=None)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'
app.config['MAX_CONTENT_LENGTH'] = 2000 * 1024 * 1024  # 2GB max

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/health')
def health():
    ffmpeg = check_ffmpeg()
    return jsonify({
        'status': 'ok',
        'version': '12.0.0',
        'ffmpeg': ffmpeg,
        'upload_folder': os.path.abspath(app.config['UPLOAD_FOLDER']),
        'output_folder': os.path.abspath(app.config['OUTPUT_FOLDER']),
    })


# ─── Unified Conversion (MP3↔M4B) ────────────────────────────

@app.route('/api/convert', methods=['POST'])
def convert():
    """Unified conversion endpoint (MP3↔M4B)."""
    try:
        file = request.files.get('source_file') or request.files.get('mp3_file')
        if not file:
            return jsonify({'error': 'No file provided'}), 400

        ext = os.path.splitext(file.filename)[1].lower()
        is_mp3 = ext == '.mp3'

        source_filename = f"{uuid.uuid4()}{ext}"
        source_path = os.path.join(app.config['UPLOAD_FOLDER'], source_filename)
        file.save(source_path)

        chapters_data = request.form.get('chapters')
        chapters = json.loads(chapters_data) if chapters_data else None

        output_ext = '.m4b' if is_mp3 else '.mp3'
        output_filename = f"{os.path.splitext(file.filename)[0]}{output_ext}"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{uuid.uuid4()}{output_ext}")

        if is_mp3:
            convert_mp3_to_m4b(source_path, output_path, chapters)
        else:
            convert_m4b_to_mp3(source_path, output_path)

        os.remove(source_path)
        return send_file(output_path, as_attachment=True, download_name=output_filename)

    except Exception as e:
        logger.error(f"Error in convert: {e}")
        return jsonify({'error': str(e)}), 500


# ─── MP3 → M4B (Explicit) ───────────────────────────────────

@app.route('/api/mp3-to-m4b', methods=['POST'])
def mp3_to_m4b():
    """Explicit MP3 to M4B endpoint."""
    try:
        file = request.files.get('mp3_file')
        if not file:
            return jsonify({'error': 'No MP3 file provided'}), 400

        source_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}.mp3")
        file.save(source_path)

        chapters_data = request.form.get('chapters')
        chapters = json.loads(chapters_data) if chapters_data else None

        output_filename = f"{os.path.splitext(file.filename)[0]}.m4b"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{uuid.uuid4()}.m4b")

        convert_mp3_to_m4b(source_path, output_path, chapters)
        os.remove(source_path)

        return send_file(output_path, as_attachment=True, download_name=output_filename)

    except Exception as e:
        logger.error(f"Error in mp3_to_m4b: {e}")
        return jsonify({'error': str(e)}), 500


# ─── Document to Audiobook (via TTS) ─────────────────────────

@app.route('/api/generate-audiobook', methods=['POST'])
def generate_audiobook():
    """Document to Audiobook using Kokoro TTS."""
    try:
        from .document_parser import parse_document
        from .tts import generate_tts
    except ImportError as e:
        return jsonify({'error': f'TTS dependencies missing: {e}. Run: pip install kokoro soundfile'}), 500

    try:
        file = request.files.get('doc_file')
        if not file:
            return jsonify({'error': 'No document provided'}), 400

        voice = request.form.get('voice', 'af_heart')
        speed = float(request.form.get('speed', 1.0))

        ext = os.path.splitext(file.filename)[1].lower()
        source_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}{ext}")
        file.save(source_path)

        doc_data = parse_document(source_path)
        text = doc_data['text']

        wav_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{uuid.uuid4()}.wav")
        generate_tts(text, wav_path, voice=voice, speed=speed)

        output_filename = f"{os.path.splitext(file.filename)[0]}.m4b"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{uuid.uuid4()}.m4b")
        convert_mp3_to_m4b(wav_path, output_path)

        os.remove(source_path)
        os.remove(wav_path)

        return send_file(output_path, as_attachment=True, download_name=output_filename)

    except Exception as e:
        logger.error(f"Error in generate_audiobook: {e}")
        return jsonify({'error': str(e)}), 500


# ─── Full Chapter-Aware Audiobook Pipeline ───────────────────

@app.route('/api/audiobook', methods=['POST'])
def audiobook_full():
    """Full chapter-aware audiobook pipeline via audiobook_builder."""
    try:
        from .audiobook_builder import build_audiobook
    except ImportError as e:
        return jsonify({'error': f'Dependencies missing: {e}'}), 500

    try:
        file = request.files.get('doc_file')
        if not file:
            return jsonify({'error': 'No document provided'}), 400

        voice = request.form.get('voice', 'af_heart')
        speed = float(request.form.get('speed', 1.0))
        quality = request.form.get('quality', '64k')

        ext = os.path.splitext(file.filename)[1].lower()
        source_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}{ext}")
        file.save(source_path)

        output_filename = f"{os.path.splitext(file.filename)[0]}.m4b"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{uuid.uuid4()}.m4b")

        result = build_audiobook(source_path, output_path, {
            'voice': voice, 'speed': speed, 'audio_quality': quality
        })

        os.remove(source_path)
        return send_file(output_path, as_attachment=True, download_name=output_filename)

    except Exception as e:
        logger.error(f"Error in audiobook_full: {e}")
        return jsonify({'error': str(e)}), 500


# ─── Preview Chapters ────────────────────────────────────────

@app.route('/api/preview-chapters', methods=['POST'])
def preview_chapters():
    """Preview detected chapters without generating audio."""
    try:
        from .audiobook_builder import preview_chapters as _preview
    except ImportError as e:
        return jsonify({'error': str(e)}), 500

    try:
        file = request.files.get('doc_file')
        if not file:
            return jsonify({'error': 'No document provided'}), 400

        ext = os.path.splitext(file.filename)[1].lower()
        source_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}{ext}")
        file.save(source_path)

        result = _preview(source_path)
        os.remove(source_path)
        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in preview_chapters: {e}")
        return jsonify({'error': str(e)}), 500


# ─── EPUB to Audiobook ──────────────────────────────────────

@app.route('/api/epub-to-audiobook', methods=['POST'])
def epub_to_audiobook():
    """EPUB to Audiobook conversion using TTS."""
    try:
        from .tts import generate_tts
        from .chapter_detector import detect_chapters
    except ImportError as e:
        return jsonify({'error': f'TTS dependencies missing: {e}'}), 500

    try:
        file = request.files.get('document_file') or request.files.get('doc_file')
        if not file:
            return jsonify({'error': 'No EPUB file provided'}), 400

        voice = request.form.get('voice', 'af_heart')
        speed = float(request.form.get('speed', 1.0))
        engine = request.form.get('engine', 'bpm4b')
        quality = request.form.get('quality', '64k')

        source_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}.epub")
        file.save(source_path)

        from .document_parser import parse_document
        doc = parse_document(source_path)
        text = doc.get('text', '')
        headings = doc.get('headings', [])

        if not text:
            return jsonify({'error': 'Could not extract text from EPUB'}), 400

        chapters = detect_chapters(text, headings)

        # Generate audio for each chapter
        from .audiobook_builder import build_audiobook
        output_filename = f"{os.path.splitext(file.filename)[0]}.m4b"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{uuid.uuid4()}.m4b")

        result = build_audiobook(source_path, output_path, {
            'voice': voice, 'speed': speed, 'audio_quality': quality
        })

        os.remove(source_path)
        return send_file(output_path, as_attachment=True, download_name=output_filename)

    except Exception as e:
        logger.error(f"Error in epub_to_audiobook: {e}")
        return jsonify({'error': str(e)}), 500


# ─── Document to EPUB ────────────────────────────────────────

@app.route('/api/document-to-epub', methods=['POST'])
def document_to_epub():
    """Convert document to EPUB format."""
    try:
        from .document_to_epub import convert_to_epub
    except ImportError as e:
        return jsonify({'error': f'Dependencies missing: {e}'}), 500

    try:
        file = request.files.get('document_file')
        if not file:
            return jsonify({'error': 'No document provided'}), 400

        title = request.form.get('title', '')
        author = request.form.get('author', '')
        language = request.form.get('language', 'en')
        description = request.form.get('description', '')

        ext = os.path.splitext(file.filename)[1].lower()
        source_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}{ext}")
        file.save(source_path)

        output_filename = f"{title or os.path.splitext(file.filename)[0]}.epub"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{uuid.uuid4()}.epub")

        result = convert_to_epub(source_path, output_path, {
            'title': title, 'author': author, 'language': language, 'description': description,
        })

        os.remove(source_path)
        return send_file(output_path, as_attachment=True, download_name=output_filename)

    except Exception as e:
        logger.error(f"Error in document_to_epub: {e}")
        return jsonify({'error': str(e)}), 500


# ─── Audio Format Converter ──────────────────────────────────

@app.route('/api/convert-audio', methods=['POST'])
def convert_audio():
    """Convert audio between formats (MP3/WAV/FLAC/AAC/OGG/ALAC)."""
    try:
        file = request.files.get('file') or request.files.get('source_file')
        if not file:
            return jsonify({'error': 'No audio file provided'}), 400

        target_format = request.form.get('target_format', 'mp3').lower()
        quality = request.form.get('quality', '192k')

        ext = os.path.splitext(file.filename)[1].lower()
        source_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}{ext}")
        file.save(source_path)

        ext_map = {'mp3': '.mp3', 'wav': '.wav', 'flac': '.flac', 'aac': '.aac', 'ogg': '.ogg', 'alac': '.m4a'}
        output_ext = ext_map.get(target_format, '.mp3')
        output_filename = f"{os.path.splitext(file.filename)[0]}{output_ext}"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{uuid.uuid4()}{output_ext}")

        result = convert_audio_format(source_path, output_path, target_format, quality)
        os.remove(source_path)

        return send_file(result, as_attachment=True, download_name=output_filename)

    except Exception as e:
        logger.error(f"Error in convert_audio: {e}")
        return jsonify({'error': str(e)}), 500


# ─── Audio Glue (Batch Merge) ────────────────────────────────

@app.route('/api/audio-glue', methods=['POST'])
def audio_glue_endpoint():
    """Merge multiple audio files into one."""
    try:
        files = request.files.getlist('files')
        if not files or len(files) < 1:
            return jsonify({'error': 'At least one audio file required'}), 400

        normalize = request.form.get('normalize', 'false').lower() == 'true'
        volume = float(request.form.get('volume', 1.0))

        input_paths = []
        for f in files:
            ext = os.path.splitext(f.filename)[1].lower()
            path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}{ext}")
            f.save(path)
            input_paths.append(path)

        output_filename = f"merged_{uuid.uuid4().hex[:8]}.m4b"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)

        audio_glue(input_paths, output_path, normalize=normalize, volume=volume)

        for p in input_paths:
            try:
                os.remove(p)
            except OSError:
                pass

        return send_file(output_path, as_attachment=True, download_name=output_filename)

    except Exception as e:
        logger.error(f"Error in audio_glue: {e}")
        return jsonify({'error': str(e)}), 500


# ─── Metadata Extract ────────────────────────────────────────

@app.route('/api/metadata/extract', methods=['POST'])
def metadata_extract():
    """Extract metadata from M4B/M4A file."""
    try:
        from .metadata import extract_metadata
    except ImportError:
        return jsonify({'error': 'Metadata module not available'}), 500

    try:
        file = request.files.get('file')
        if not file:
            return jsonify({'error': 'No file provided'}), 400

        ext = os.path.splitext(file.filename)[1].lower()
        source_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}{ext}")
        file.save(source_path)

        metadata = extract_metadata(source_path)
        os.remove(source_path)

        return jsonify(metadata)

    except Exception as e:
        logger.error(f"Error in metadata_extract: {e}")
        return jsonify({'error': str(e)}), 500


# ─── Metadata Apply ──────────────────────────────────────────

@app.route('/api/metadata/apply', methods=['POST'])
def metadata_apply():
    """Apply metadata and cover art to M4B/M4A file."""
    try:
        from .metadata import apply_metadata
    except ImportError:
        return jsonify({'error': 'Metadata module not available'}), 500

    try:
        file = request.files.get('file')
        if not file:
            return jsonify({'error': 'No file provided'}), 400

        metadata_json = request.form.get('metadata', '{}')
        metadata = json.loads(metadata_json)
        cover_base64 = request.form.get('cover_base64')

        ext = os.path.splitext(file.filename)[1].lower()
        source_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}{ext}")
        file.save(source_path)

        output_filename = f"metadata_{os.path.splitext(file.filename)[0]}{ext}"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{uuid.uuid4()}{ext}")

        apply_metadata(source_path, output_path, metadata, cover_base64)
        os.remove(source_path)

        return send_file(output_path, as_attachment=True, download_name=output_filename)

    except Exception as e:
        logger.error(f"Error in metadata_apply: {e}")
        return jsonify({'error': str(e)}), 500


# ─── Metadata Lookup (Open Library) ──────────────────────────

@app.route('/api/metadata/lookup', methods=['POST'])
def metadata_lookup():
    """Lookup book metadata from Open Library."""
    try:
        from .metadata import lookup_open_library
    except ImportError:
        return jsonify({'error': 'Metadata module not available'}), 500

    try:
        data = request.get_json() or {}
        title = data.get('title', '')
        author = data.get('author', '')

        results = lookup_open_library(title, author)
        return jsonify({'results': results, 'count': len(results)})

    except Exception as e:
        logger.error(f"Error in metadata_lookup: {e}")
        return jsonify({'error': str(e)}), 500


# ─── Voices List ─────────────────────────────────────────────

@app.route('/api/voices')
def list_voices():
    """List available TTS voices."""
    try:
        from .tts import AVAILABLE_VOICES
        return jsonify({'voices': AVAILABLE_VOICES})
    except ImportError:
        return jsonify({'voices': []})


# ─── Folder to M4B ───────────────────────────────────────────

@app.route('/api/folder-to-m4b', methods=['POST'])
def folder_to_m4b_endpoint():
    """Convert uploaded audio files to a single M4B with auto-chapters."""
    try:
        files = request.files.getlist('files')
        if not files or len(files) < 1:
            return jsonify({'error': 'At least one audio file required'}), 400

        quality = request.form.get('quality', '128k')

        # Save all files to a temp folder
        folder_path = tf.mkdtemp(prefix='bpm4b_folder_')
        try:
            for f in files:
                safe_name = f"{uuid.uuid4().hex[:8]}_{f.filename}"
                f.save(os.path.join(folder_path, safe_name))

            output_filename = f"folder_audiobook_{uuid.uuid4().hex[:8]}.m4b"
            output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)

            result = folder_to_m4b(folder_path, output_path, {
                'audio_quality': quality,
            })

            return send_file(output_path, as_attachment=True, download_name=output_filename)

        finally:
            shutil.rmtree(folder_path, ignore_errors=True)

    except Exception as e:
        logger.error(f"Error in folder_to_m4b: {e}")
        return jsonify({'error': str(e)}), 500


# ─── Cleanup (old files) ─────────────────────────────────────

@app.route('/api/cleanup', methods=['POST'])
def cleanup():
    """Clean up old uploaded and output files (older than 1 hour)."""
    cutoff = time.time() - 3600  # 1 hour
    cleaned = 0
    for folder in [app.config['UPLOAD_FOLDER'], app.config['OUTPUT_FOLDER']]:
        for fname in os.listdir(folder):
            fpath = os.path.join(folder, fname)
            if os.path.isfile(fpath):
                if os.path.getmtime(fpath) < cutoff:
                    try:
                        os.remove(fpath)
                        cleaned += 1
                    except OSError:
                        pass
    return jsonify({'cleaned': cleaned})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
