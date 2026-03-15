# MP3 to M4B Audiobook Converter (bpm4b)

A Flask-based web application for converting MP3 files to M4B audiobook format with chapter support.

**Install and run with:** `pip install bpm4b` then `bpm4b`
# BPM4B - Professional AI Audiobook Suite (v9.0.0)

A professional multimedia processing suite for converting MP3 to M4B, M4B to MP3, and generating AI Audiobooks from documents with high-fidelity TTS and automatic chapter support.

## Installation

```bash
pip install bpm4b
```

**For local development:**
```bash
git clone https://github.com/jdjchelp-jpg/bpm4b.git
cd bpm4b
pip install -e .
```

## Features

### 🎯 Document to Audiobook (AI Gen)
- Convert PDF, DOCX, TXT, and EPUB to high-quality audiobooks.
- Powered by Kokoro-82M High-Fidelity local TTS (no Cloud costs).
- Automatic chapter detection and timing.

### 📁 Unified Media Conversion
- **MP3 to M4B**: Create chapterized audiobooks for Apple Books/Audible.
- **M4B to MP3**: Convert audiobooks to standard high-quality MP3 (128k+).
- Integrated FFmpeg processing for lossy/lossless conversion.

### ⏱ Automatic Chapter Builder
- Interactive timestamp generator.
- Support for HH:MM:SS and Seconds format.
- Batch import/export of chapter metadata.

### 🚀 Premium Web Interface
- Modern Glassmorphism UI.
- Real-time progress monitoring.
- Drag-and-drop workflow.

## Usage

### Web Interface
```bash
bpm4b web
```
Then navigate to http://localhost:5000.

### CLI Commands
```bash
# Convert MP3 to M4B
bpm4b convert input.mp3 output.m4b

# Convert M4B to MP3
bpm4b convert archive.m4b audio.mp3

# Generate AI Audiobook from PDF
bpm4b audiobook book.pdf book.m4b --voice af_heart
```

## Requirements
- Python 3.8+
- FFmpeg (Installed and in PATH)

## API Endpoints

### POST /api/mp3-to-m4b
Converts an MP3 file to M4B with optional chapters.

**Form Data:**
- `mp3_file`: The MP3 file to convert
- `chapters` (optional): JSON array of chapter objects. `start_time` accepts seconds (number) or MM:SS format (string):
```json
[
  {"title": "Chapter 1", "start_time": 0},
  {"title": "Chapter 2", "start_time": "6:30"},
  {"title": "Chapter 3", "start_time": 3600}
]
```

**Response:**
Returns an M4B file as a download.

## Project Structure

```
.
├── bpm4b/              # Main package directory
│   ├── __init__.py    # Package initialization
│   ├── app.py         # Flask application (for local development)
│   ├── cli.py         # Command-line interface entry point
│   ├── core.py        # Shared core functions
│   ├── api/
│   │   ├── __init__.py
│   │   └── index.py   # Vercel serverless function
│   └── templates/
│       └── index.html # Frontend interface
├── setup.py           # Package installation configuration
├── vercel.json        # Vercel configuration
├── requirements.txt   # Python dependencies
├── uploads/           # Temporary uploaded files (created automatically)
├── outputs/           # Generated files (created automatically)
└── README.md          # This file
```

## Notes

- Maximum file size for uploads: 100MB
- Temporary files are cleaned up automatically
- M4B output files can be large (typically 0.96-2GB per hour of audio depending on bitrate)
- The default audio bitrate is 64kbps AAC, which provides good quality for speech

## License

MIT