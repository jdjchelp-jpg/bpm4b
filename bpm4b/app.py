import os
import uuid
import json
import logging
import time
import tempfile as tf
import shutil
from flask import Flask, request, send_file, jsonify, render_template, Response, stream_with_context
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
        'version': '13.0.0',
        'ffmpeg': ffmpeg,
        'upload_folder': os.path.abspath(app.config['UPLOAD_FOLDER']),
        'output_folder': os.path.abspath(app.config['OUTPUT_FOLDER']),
    })


# ─── Unified Conversion (MP3↔M4B) ────────────────────────────

@app.route('/api/convert', methods=['POST'])
def convert():
    """Unified conversion endpoint (MP3↔M4B)."""
    from .job_database import get_db
    try:
        file = request.files.get('source_file') or request.files.get('mp3_file')
        if not file:
            return jsonify({'error': 'No file provided'}), 400

        ext = os.path.splitext(file.filename)[1].lower()
        is_mp3 = ext == '.mp3'
        job_id = str(uuid.uuid4())

        source_filename = f"{uuid.uuid4()}{ext}"
        source_path = os.path.join(app.config['UPLOAD_FOLDER'], source_filename)
        file.save(source_path)

        chapters_data = request.form.get('chapters')
        chapters = json.loads(chapters_data) if chapters_data else None

        output_ext = '.m4b' if is_mp3 else '.mp3'
        output_filename = f"{os.path.splitext(file.filename)[0]}{output_ext}"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{uuid.uuid4()}{output_ext}")

        # Log job
        db = get_db()
        db.create_job(job_id, 'convert', source_path, output_path)

        start = time.time()
        if is_mp3:
            convert_mp3_to_m4b(source_path, output_path, chapters)
        else:
            convert_m4b_to_mp3(source_path, output_path)

        elapsed = time.time() - start
        db.complete_job(job_id, output_path, processing_time_seconds=elapsed,
                        file_size_bytes=os.path.getsize(output_path))

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


# ─── Document to Audiobook (via abogen) ──────────────────────

@app.route('/api/generate-audiobook', methods=['POST'])
def generate_audiobook():
    """Document to Audiobook using abogen + BPM4B preprocessing."""
    from .abogen_integration import run_abogen, is_abogen_available
    from .job_database import get_db

    if not is_abogen_available():
        return jsonify({'error': 'abogen not found. Install: pip install abogen'}), 500

    try:
        file = request.files.get('doc_file')
        if not file:
            return jsonify({'error': 'No document provided'}), 400

        voice = request.form.get('voice', 'af_heart')
        speed = float(request.form.get('speed', 1.0))
        job_id = str(uuid.uuid4())

        ext = os.path.splitext(file.filename)[1].lower()
        source_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}{ext}")
        file.save(source_path)

        output_filename = f"{os.path.splitext(file.filename)[0]}.m4b"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{uuid.uuid4()}.m4b")

        db = get_db()
        db.create_job(job_id, 'abogen', source_path, output_path,
                      {'voice': voice, 'speed': speed})

        result = run_abogen(source_path, output_path, {
            'voice': voice, 'speed': speed, 'format': 'm4b'
        })

        db.complete_job(job_id, output_path,
                       file_size_bytes=os.path.getsize(output_path))

        os.remove(source_path)
        return send_file(output_path, as_attachment=True, download_name=output_filename)

    except Exception as e:
        logger.error(f"Error in generate_audiobook: {e}")
        return jsonify({'error': str(e)}), 500


# ─── Full Chapter-Aware Audiobook Pipeline ───────────────────

@app.route('/api/audiobook', methods=['POST'])
def audiobook_full():
    """Full chapter-aware audiobook pipeline."""
    # Redirect to abogen endpoint
    return generate_audiobook()


# ─── Preview Chapters ────────────────────────────────────────

@app.route('/api/preview-chapters', methods=['POST'])
def preview_chapters():
    """Preview detected chapters without generating audio."""
    from .abogen_integration import preprocess_for_abogen
    try:
        file = request.files.get('doc_file')
        if not file:
            return jsonify({'error': 'No document provided'}), 400

        ext = os.path.splitext(file.filename)[1].lower()
        source_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}{ext}")
        file.save(source_path)

        result = preprocess_for_abogen(source_path, {
            'resolve_roman': True,
            'stat_block_mode': 'summarize',
        })
        os.remove(source_path)
        return jsonify({
            'chapters': result['chapters'],
            'chapter_count': result['chapter_count'],
            'total_chars': result['total_chars'],
            'stat_blocks_found': result.get('stat_blocks_found', 0),
        })

    except Exception as e:
        logger.error(f"Error in preview_chapters: {e}")
        return jsonify({'error': str(e)}), 500


# ─── BPM4B Magic (Preprocessing) ────────────────────────────

@app.route('/api/magic', methods=['POST'])
def magic_endpoint():
    """Apply BPM4B preprocessing magic to a document."""
    from .abogen_integration import preprocess_for_abogen
    try:
        file = request.files.get('document_file')
        if not file:
            return jsonify({'error': 'No document provided'}), 400

        ext = os.path.splitext(file.filename)[1].lower()
        source_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}{ext}")
        file.save(source_path)

        options = {
            'resolve_roman': request.form.get('resolve_roman', 'true').lower() == 'true',
            'stat_block_mode': request.form.get('stat_block_mode', 'summarize'),
        }

        result = preprocess_for_abogen(source_path, options)
        os.remove(source_path)

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in magic: {e}")
        return jsonify({'error': str(e)}), 500


# ─── EPUB to Audiobook ──────────────────────────────────────

@app.route('/api/epub-to-audiobook', methods=['POST'])
def epub_to_audiobook():
    """EPUB to Audiobook conversion using abogen."""
    from .abogen_integration import run_abogen
    try:
        file = request.files.get('document_file') or request.files.get('doc_file')
        if not file:
            return jsonify({'error': 'No EPUB file provided'}), 400

        voice = request.form.get('voice', 'af_heart')
        speed = float(request.form.get('speed', 1.0))

        source_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}.epub")
        file.save(source_path)

        output_filename = f"{os.path.splitext(file.filename)[0]}.m4b"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{uuid.uuid4()}.m4b")

        run_abogen(source_path, output_path, {
            'voice': voice, 'speed': speed, 'format': 'm4b'
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
    """Merge multiple audio files into one (zero-copy by default)."""
    from .splicer import splice_audio_files
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

        splice_audio_files(input_paths, output_path, stream_copy=not normalize,
                          normalize=normalize, volume=volume)

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

        # Also extract chapters if available
        from .cover_art import extract_chapters_from_m4b
        chapters = extract_chapters_from_m4b(source_path)
        if chapters:
            metadata['chapters'] = chapters
            metadata['chapter_count'] = len(chapters)

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
        use_cache = request.form.get('cache', 'false').lower() == 'true'

        folder_path = tf.mkdtemp(prefix='bpm4b_folder_')
        try:
            for f in files:
                safe_name = f"{uuid.uuid4().hex[:8]}_{f.filename}"
                f.save(os.path.join(folder_path, safe_name))

            output_filename = f"folder_audiobook_{uuid.uuid4().hex[:8]}.m4b"
            output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)

            result = folder_to_m4b(folder_path, output_path, {
                'audio_quality': quality,
                'cache_enabled': use_cache,
            })

            return send_file(output_path, as_attachment=True, download_name=output_filename)

        finally:
            shutil.rmtree(folder_path, ignore_errors=True)

    except Exception as e:
        logger.error(f"Error in folder_to_m4b: {e}")
        return jsonify({'error': str(e)}), 500


# ─── Cover Art ───────────────────────────────────────────────

@app.route('/api/cover/extract', methods=['POST'])
def cover_extract():
    """Extract cover art from audio file."""
    from .cover_art import extract_cover_art
    try:
        file = request.files.get('file')
        if not file:
            return jsonify({'error': 'No file provided'}), 400

        ext = os.path.splitext(file.filename)[1].lower()
        source_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}{ext}")
        file.save(source_path)

        cover_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{uuid.uuid4()}_cover.jpg")
        data = extract_cover_art(source_path, cover_path)
        os.remove(source_path)

        if data:
            return send_file(cover_path, as_attachment=True,
                           download_name=f"{os.path.splitext(file.filename)[0]}_cover.jpg")
        return jsonify({'error': 'No cover art found'}), 404

    except Exception as e:
        logger.error(f"Error in cover_extract: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/cover/inject', methods=['POST'])
def cover_inject():
    """Inject cover art into audio file."""
    from .cover_art import inject_cover_art
    try:
        audio_file = request.files.get('audio_file')
        cover_file = request.files.get('cover_file')
        if not audio_file or not cover_file:
            return jsonify({'error': 'Both audio_file and cover_file required'}), 400

        audio_ext = os.path.splitext(audio_file.filename)[1].lower()
        audio_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}{audio_ext}")
        audio_file.save(audio_path)

        cover_ext = os.path.splitext(cover_file.filename)[1].lower()
        cover_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}{cover_ext}")
        cover_file.save(cover_path)

        output_ext = audio_ext or '.m4b'
        output_filename = f"with_cover_{audio_file.filename}"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{uuid.uuid4()}{output_ext}")

        inject_cover_art(audio_path, cover_path, output_path)

        os.remove(audio_path)
        os.remove(cover_path)

        return send_file(output_path, as_attachment=True, download_name=output_filename)

    except Exception as e:
        logger.error(f"Error in cover_inject: {e}")
        return jsonify({'error': str(e)}), 500


# ─── Demux (M4B → MP3 chapters) ────────────────────────────

@app.route('/api/demux', methods=['POST'])
def demux_endpoint():
    """Split M4B into individual MP3 chapter tracks."""
    from .demuxer import demux_m4b_to_mp3
    from .path_utils import temp_dir, cleanup_dir
    try:
        file = request.files.get('file')
        if not file:
            return jsonify({'error': 'No file provided'}), 400

        quality = request.form.get('quality', '128k')

        source_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}.m4b")
        file.save(source_path)

        output_dir = temp_dir('bpm4b_demux_')
        try:
            results = demux_m4b_to_mp3(source_path, output_dir, quality=quality)

            # Zip the results
            import zipfile
            zip_filename = f"{os.path.splitext(file.filename)[0]}_chapters.zip"
            zip_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{uuid.uuid4()}.zip")
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for r in results:
                    if r.get('output_path') and os.path.exists(r['output_path']):
                        zf.write(r['output_path'], os.path.basename(r['output_path']))

            return send_file(zip_path, as_attachment=True, download_name=zip_filename)

        finally:
            cleanup_dir(output_dir)
            os.remove(source_path)

    except Exception as e:
        logger.error(f"Error in demux: {e}")
        return jsonify({'error': str(e)}), 500


# ─── SSE Progress Stream ─────────────────────────────────────

@app.route('/api/progress/stream')
def progress_stream():
    """SSE endpoint for real-time progress updates."""
    from .sse_progress import get_progress_manager
    job_id = request.args.get('job_id', '')

    if not job_id:
        return jsonify({'error': 'job_id query parameter required'}), 400

    mgr = get_progress_manager()
    return Response(
        stream_with_context(mgr.get_events_generator(job_id)),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        }
    )


@app.route('/api/progress/status', methods=['GET'])
def progress_status():
    """Get the current status of a job."""
    from .sse_progress import get_progress_manager
    job_id = request.args.get('job_id', '')
    if not job_id:
        return jsonify({'error': 'job_id required'}), 400
    status = get_progress_manager().get_job_status(job_id)
    if status:
        return jsonify(status)
    return jsonify({'error': 'Job not found'}), 404


# ─── Job History ─────────────────────────────────────────────

@app.route('/api/jobs', methods=['GET'])
def list_jobs():
    """List conversion job history."""
    from .job_database import get_db
    limit = int(request.args.get('limit', 50))
    status = request.args.get('status')
    job_type = request.args.get('type')
    jobs = get_db().list_jobs(limit=limit, status=status, job_type=job_type)
    return jsonify({'jobs': jobs, 'count': len(jobs)})


@app.route('/api/jobs/stats', methods=['GET'])
def job_stats():
    """Get job history statistics."""
    from .job_database import get_db
    return jsonify(get_db().get_stats())


@app.route('/api/jobs/clear', methods=['POST'])
def clear_jobs():
    """Clear job history."""
    from .job_database import get_db
    count = get_db().clear_history()
    return jsonify({'cleared': count})


# ─── Pre-Flight Storage Estimate ────────────────────────────

@app.route('/api/estimate', methods=['POST'])
def estimate_endpoint():
    """Estimate output file size before conversion."""
    from .ffmpeg_utils import estimate_output_size, estimate_batch_output_size
    try:
        files = request.files.getlist('files')
        if not files:
            return jsonify({'error': 'No files provided'}), 400

        bitrate = int(request.form.get('bitrate', 64))
        output_format = request.form.get('format', 'm4b')

        # Save files temporarily
        file_paths = []
        for f in files:
            path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}_{f.filename}")
            f.save(path)
            file_paths.append(path)

        try:
            if len(file_paths) == 1:
                est = estimate_output_size(file_paths[0], bitrate, output_format)
            else:
                est = estimate_batch_output_size(file_paths, bitrate, output_format)
            return jsonify(est)
        finally:
            for p in file_paths:
                try:
                    os.remove(p)
                except OSError:
                    pass

    except Exception as e:
        logger.error(f"Error in estimate: {e}")
        return jsonify({'error': str(e)}), 500


# ─── Silence Chapter Detection ──────────────────────────────

@app.route('/api/silence-chapter', methods=['POST'])
def silence_chapter_endpoint():
    """Auto-detect chapters from silence regions."""
    from .ffmpeg_utils import auto_chapter_from_silence
    try:
        file = request.files.get('file')
        if not file:
            return jsonify({'error': 'No file provided'}), 400

        threshold = request.form.get('threshold', '-30dB')
        min_silence = float(request.form.get('min_silence', 2.0))
        min_chapter = float(request.form.get('min_chapter', 60.0))

        source_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}.wav")
        file.save(source_path)

        try:
            chapters = auto_chapter_from_silence(
                source_path,
                noise_threshold=threshold,
                min_silence_duration=min_silence,
                min_chapter_duration=min_chapter,
            )
            return jsonify({'chapters': chapters, 'count': len(chapters)})
        finally:
            os.remove(source_path)

    except Exception as e:
        logger.error(f"Error in silence_chapter: {e}")
        return jsonify({'error': str(e)}), 500


# ─── Trim Silence ────────────────────────────────────────────

@app.route('/api/trim', methods=['POST'])
def trim_endpoint():
    """Trim border silence from audio."""
    from .ffmpeg_utils import trim_border_silence, trim_all_silence
    try:
        file = request.files.get('file')
        if not file:
            return jsonify({'error': 'No file provided'}), 400

        mode = request.form.get('mode', 'borders')
        threshold = request.form.get('threshold', '-50dB')
        min_silence = float(request.form.get('min_silence', 0.1))

        ext = os.path.splitext(file.filename)[1].lower()
        source_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}{ext}")
        file.save(source_path)

        output_ext = ext or '.wav'
        output_filename = f"trimmed_{file.filename}"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{uuid.uuid4()}{output_ext}")

        if mode == 'all':
            trim_all_silence(source_path, output_path, threshold, min_silence)
        else:
            trim_border_silence(source_path, output_path, threshold, min_silence)

        os.remove(source_path)
        return send_file(output_path, as_attachment=True, download_name=output_filename)

    except Exception as e:
        logger.error(f"Error in trim: {e}")
        return jsonify({'error': str(e)}), 500


# ─── Profile ─────────────────────────────────────────────────

@app.route('/api/profile', methods=['GET', 'POST'])
def profile_endpoint():
    """Manage processing profiles."""
    from .profile_manager import load_profile, save_profile, list_saved_profiles
    if request.method == 'GET':
        profiles = list_saved_profiles()
        config = load_profile()
        return jsonify({
            'current_config': config,
            'available_profiles': profiles,
        })

    # POST: save a profile
    data = request.get_json() or {}
    profile_path = data.get('path', '')
    profile_data = data.get('profile', {})
    if profile_path and profile_data:
        save_profile(profile_data, profile_path)
        return jsonify({'saved': True, 'path': profile_path})
    return jsonify({'error': 'path and profile data required'}), 400


# ─── System Info ─────────────────────────────────────────────

@app.route('/api/system', methods=['GET'])
def system_info():
    """Get system resource information."""
    from .concurrency_guard import get_system_summary, get_memory_usage_pct
    from .ffmpeg_utils import get_ffmpeg_info, check_ffmpeg_compat
    from .abogen_integration import is_abogen_available
    import platform

    return jsonify({
        'platform': platform.system(),
        'release': platform.release(),
        'python': platform.python_version(),
        'system': get_system_summary(),
        'memory_usage_pct': get_memory_usage_pct(),
        'ffmpeg': get_ffmpeg_info(),
        'ffmpeg_compat': check_ffmpeg_compat(),
        'abogen_available': is_abogen_available(),
    })


# ─── Chapter Import ──────────────────────────────────────────

@app.route('/api/chapters/import', methods=['POST'])
def chapters_import():
    """Import chapters from a file (CUE, Audacity, VTT, CSV, JSON)."""
    from .chapter_io import import_chapters
    try:
        file = request.files.get('file')
        if not file:
            return jsonify({'error': 'No file provided'}), 400

        ext = os.path.splitext(file.filename)[1].lower()
        source_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}{ext}")
        file.save(source_path)

        try:
            chapters = import_chapters(source_path)
            return jsonify({'chapters': chapters, 'count': len(chapters)})
        finally:
            os.remove(source_path)

    except Exception as e:
        logger.error(f"Error in chapters_import: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/chapters/export', methods=['POST'])
def chapters_export():
    """Export chapters to a file format."""
    from .chapter_io import export_chapters
    try:
        data = request.get_json() or {}
        chapters = data.get('chapters', [])
        fmt = data.get('format', 'vtt')
        if not chapters:
            return jsonify({'error': 'No chapters provided'}), 400

        ext_map = {'vtt': '.vtt', 'cue': '.cue', 'csv': '.csv', 'json': '.json', 'chapters.txt': '.txt'}
        output_ext = ext_map.get(fmt, '.txt')
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"chapters_{uuid.uuid4().hex[:8]}{output_ext}")

        export_chapters(chapters, output_path, format=fmt)
        return send_file(output_path, as_attachment=True,
                        download_name=f"chapters{output_ext}")

    except Exception as e:
        logger.error(f"Error in chapters_export: {e}")
        return jsonify({'error': str(e)}), 500


# ─── Cleanup (old files) ─────────────────────────────────────

@app.route('/api/cleanup', methods=['POST'])
def cleanup():
    """Clean up old uploaded and output files (older than 1 hour)."""
    cutoff = time.time() - 3600
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
