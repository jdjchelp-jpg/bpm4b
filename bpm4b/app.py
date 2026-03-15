import os
import uuid
import json
import logging
import threading
from flask import Flask, request, send_file, jsonify, render_template
from .core import convert_mp3_to_m4b, convert_m4b_to_mp3, parse_time_to_seconds

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, 
            template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
            static_folder=None)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'
app.config['MAX_CONTENT_LENGTH'] = 2000 * 1024 * 1024  # 2GB max

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/convert', methods=['POST'])
def convert():
    """Unified conversion endpoint"""
    try:
        file = request.files.get('source_file') or request.files.get('mp3_file')
        if not file:
            return jsonify({'error': 'No file provided'}), 400

        # Determine type
        ext = os.path.splitext(file.filename)[1].lower()
        is_mp3 = ext == '.mp3'
        
        # Save temp
        source_filename = f"{uuid.uuid4()}{ext}"
        source_path = os.path.join(app.config['UPLOAD_FOLDER'], source_filename)
        file.save(source_path)

        # Chapters
        chapters_data = request.form.get('chapters')
        chapters = json.loads(chapters_data) if chapters_data else None

        # Output
        output_ext = '.m4b' if is_mp3 else '.mp3'
        output_filename = f"{os.path.splitext(file.filename)[0]}{output_ext}"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{uuid.uuid4()}{output_ext}")

        if is_mp3:
            convert_mp3_to_m4b(source_path, output_path, chapters)
        else:
            convert_m4b_to_mp3(source_path, output_path)

        # Cleanup
        os.remove(source_path)

        return send_file(output_path, as_attachment=True, download_name=output_filename)

    except Exception as e:
        logger.error(f"Error in convert: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate-audiobook', methods=['POST'])
def generate_audiobook():
    """Document to Audiobook using Kokoro TTS"""
    try:
        file = request.files.get('doc_file')
        if not file:
            return jsonify({'error': 'No document provided'}), 400

        voice = request.form.get('voice', 'af_heart')
        
        # Save temp
        ext = os.path.splitext(file.filename)[1].lower()
        source_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}{ext}")
        file.save(source_path)

        # Parse Text
        doc_data = parse_document(source_path)
        text = doc_data['text']
        
        # Generate Audio (WAV first)
        wav_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{uuid.uuid4()}.wav")
        generate_tts(text, wav_path, voice=voice)

        # Convert WAV to M4B
        output_filename = f"{os.path.splitext(file.filename)[0]}.m4b"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"{uuid.uuid4()}.m4b")
        convert_mp3_to_m4b(wav_path, output_path)

        # Cleanup
        os.remove(source_path)
        os.remove(wav_path)

        return send_file(output_path, as_attachment=True, download_name=output_filename)

    except Exception as e:
        logger.error(f"Error in generate_audiobook: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)