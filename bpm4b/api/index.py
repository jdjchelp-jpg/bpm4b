import os
import sys
import uuid
import subprocess
import json
import logging
from datetime import datetime
from flask import Flask, request, send_file, jsonify, render_template

# Add parent directory to path for imports when running as Vercel function
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import shared core functions
from bpm4b.core import convert_mp3_to_m4b

app = Flask(__name__)

# Use /tmp for Vercel's ephemeral storage
app.config['UPLOAD_FOLDER'] = '/tmp/uploads'
app.config['OUTPUT_FOLDER'] = '/tmp/outputs'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/mp3-to-m4b', methods=['POST'])
def mp3_to_m4b():
    """Convert MP3 to M4B with chapters"""
    try:
        # Check if file was uploaded
        if 'mp3_file' not in request.files:
            return jsonify({'error': 'No MP3 file provided'}), 400

        mp3_file = request.files['mp3_file']
        if mp3_file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        # Get chapter data if provided
        chapters_data = request.form.get('chapters')
        chapters = None
        if chapters_data:
            try:
                chapters = json.loads(chapters_data)
            except:
                chapters = None

        # Save uploaded file
        mp3_filename = f"{uuid.uuid4()}.mp3"
        mp3_path = os.path.join(app.config['UPLOAD_FOLDER'], mp3_filename)
        mp3_file.save(mp3_path)

        # Create output filename
        output_filename = f'{os.path.splitext(mp3_file.filename)[0]}.m4b'
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)

        # Convert to M4B
        logger.info(f"Converting {mp3_path} to {output_path}")
        convert_mp3_to_m4b(mp3_path, output_path, chapters)

        # Cleanup uploaded file
        os.remove(mp3_path)

        # Send the file
        return send_file(
            output_path,
            as_attachment=True,
            download_name=output_filename,
            mimetype='audio/x-m4b'
        )

    except Exception as e:
        logger.error(f"Error in mp3_to_m4b: {e}")
        return jsonify({'error': str(e)}), 500

# This is the entry point for Vercel
handler = app