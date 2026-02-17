import os
import uuid
import zipfile
import tempfile
import subprocess
import json
from datetime import datetime
from flask import Flask, request, send_file, jsonify, render_template
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

# Check for FFmpeg at startup
try:
    subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    logger.info("FFmpeg is available")
except (subprocess.CalledProcessError, FileNotFoundError):
    logger.warning("FFmpeg is not installed or not in PATH. MP3 to M4B conversion will not work.")

def is_valid_url(url):
    """Check if URL is valid and has a supported scheme"""
    try:
        result = urlparse(url)
        return all([result.scheme in ['http', 'https'], result.netloc])
    except:
        return False

def download_website(url, max_pages=50):
    """Download a website and return the directory path"""
    # Create a unique directory for this download
    session_id = str(uuid.uuid4())
    download_dir = os.path.join(tempfile.gettempdir(), f'website_{session_id}')
    os.makedirs(download_dir, exist_ok=True)

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        visited = set()
        to_visit = [url]
        pages_downloaded = 0

        while to_visit and pages_downloaded < max_pages:
            current_url = to_visit.pop(0)

            if current_url in visited:
                continue

            try:
                logger.info(f"Downloading: {current_url}")
                response = requests.get(current_url, headers=headers, timeout=10)
                if response.status_code != 200:
                    continue

                # Parse the page
                soup = BeautifulSoup(response.content, 'html.parser')

                # Determine the file path
                parsed = urlparse(current_url)
                relative_path = parsed.path.lstrip('/')
                if not relative_path or relative_path.endswith('/'):
                    relative_path = os.path.join(relative_path, 'index.html')
                elif '.' not in os.path.basename(relative_path):
                    relative_path = os.path.join(relative_path, 'index.html')

                file_path = os.path.join(download_dir, relative_path)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)

                # Save the HTML
                with open(file_path, 'wb') as f:
                    f.write(response.content)

                pages_downloaded += 1
                visited.add(current_url)

                # Find links to other pages on the same domain
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    absolute_url = urljoin(current_url, href)
                    parsed_link = urlparse(absolute_url)

                    # Only follow links to the same domain
                    if parsed_link.netloc == parsed.netloc:
                        if absolute_url not in visited and absolute_url not in to_visit:
                            to_visit.append(absolute_url)

            except Exception as e:
                logger.error(f"Error downloading {current_url}: {e}")
                continue

        return download_dir

    except Exception as e:
        logger.error(f"Error in download_website: {e}")
        raise

def create_zip_from_directory(directory_path, output_path):
    """Create a ZIP file from a directory"""
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                file_path = os.path.join(root, file)
                arc_name = os.path.relpath(file_path, directory_path)
                zipf.write(file_path, arc_name)

def convert_mp3_to_m4b(mp3_path, output_path, chapters=None):
    """Convert MP3 to M4B with optional chapters using ffmpeg"""
    try:
        # Build ffmpeg command
        cmd = ['ffmpeg', '-i', mp3_path, '-c:a', 'aac', '-b:a', '64k']

        # Add chapter metadata if provided
        if chapters:
            # Create a chapter file for ffmpeg
            chapter_file = os.path.join(os.path.dirname(output_path), 'chapters.txt')
            with open(chapter_file, 'w') as f:
                f.write(';FFMETADATA1\n')
                for i, chapter in enumerate(chapters):
                    start_time = chapter['start_time']
                    end_time = chapter['end_time'] if i < len(chapters) - 1 else None

                    f.write(f'[CHAPTER]\n')
                    f.write(f'TIMEBASE=1/1000\n')
                    f.write(f'START={int(start_time * 1000)}\n')
                    if end_time:
                        f.write(f'END={int(end_time * 1000)}\n')
                    f.write(f'title={chapter["title"]}\n\n')

            cmd.extend(['-i', chapter_file, '-map_metadata', '1'])

        cmd.append(output_path)

        # Run ffmpeg
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise Exception(f"FFmpeg error: {result.stderr}")

        return True

    except Exception as e:
        logger.error(f"Error in convert_mp3_to_m4b: {e}")
        raise

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/website-to-zip', methods=['POST'])
def website_to_zip():
    """Convert a website URL to a ZIP file"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()

        if not url:
            return jsonify({'error': 'URL is required'}), 400

        if not is_valid_url(url):
            return jsonify({'error': 'Invalid URL'}), 400

        # Create output ZIP file
        output_filename = f'website_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)

        # Download website
        logger.info(f"Starting download of {url}")
        download_dir = download_website(url)

        # Create ZIP
        logger.info(f"Creating ZIP file: {output_path}")
        create_zip_from_directory(download_dir, output_path)

        # Cleanup download directory
        import shutil
        shutil.rmtree(download_dir)

        # Send the file
        return send_file(
            output_path,
            as_attachment=True,
            download_name=output_filename,
            mimetype='application/zip'
        )

    except Exception as e:
        logger.error(f"Error in website_to_zip: {e}")
        return jsonify({'error': str(e)}), 500

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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)