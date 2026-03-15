# BPM4B - Professional Multimedia Suite (v9.0.0)

A professional multimedia processing suite for converting MP3 to M4B, M4B to MP3, and generating AI Audiobooks with high-fidelity TTS and automatic chapter support.

**Available in two versions:**
- **Python** (Flask): `pip install bpm4b` then `bpm4b`
- **Node.js** (Express): `npm install -g bpm4b` then `bpm4b`

## Installation

### Python Version (Original)
```bash
pip install bpm4b
bpm4b web
```

### Node.js Version
```bash
npm install -g bpm4b
bpm4b web
```

**Or for local development:**
```bash
git clone https://github.com/jdjchelp-jpg/nodebpm4b.git
cd nodebpm4b
npm install
npm start
```

**Update:**
```bash
# Update Python version
pip install --upgrade bpm4b

# Update Node.js version
npm update -g bpm4b
```

## Features

### 🎯 Unified Smart Mode
- Single toggle switch: Conversion Mode vs Chapter Builder Only
- Automatic chapter attachment to MKV/M4B output when conversion mode is ON
- Standalone timestamp generator when mode is OFF

### 📁 File Conversion Section
- **MP3 to M4B**: Convert MP3 files to audiobook format with embedded chapters
- **M4B to MP3**: High-fidelity conversion from M4B/M4A containers to MP3 (NEW in v9)
- **Document to Audiobook**: Generate high-quality voiceovers from PDF/Text using Kokoro-82M AI (NEW in v9)
- Drag-and-drop file upload for all tools
- Real-time progress monitoring with SSE (Server-Sent Events)
- Visual progress bar and live terminal logging

### ⏱ Automatic Chapter Builder
- **Always enabled** - core functionality
- Enter chapter title and duration (minutes or seconds toggle)
- System automatically:
  - Converts input to proper format
  - Accumulates duration to cumulative total
  - Calculates next chapter start timestamp
  - Generates proper HH:MM:SS format
- No manual math required - all timestamps auto-generate
- Batch import/export chapter lists
- Real-time preview updates

### ⚙ Settings Panel
- Dark / Light mode toggle
- Modern toggle switches (not checkboxes)
- Glassmorphism card design
- Smooth animations and transitions
- Responsive layout optimized for desktop

### 🚀 Performance Improvements
- Faster parsing with optimized algorithms
- Non-blocking UI with background conversion
- Proper error handling and validation
- File size validation before processing
- Automatic cleanup of temporary files

### 📋 Professional Features
- Copy-to-clipboard buttons for generated commands
- Real-time updating preview panel
- FFmpeg command preview (self-service mode)
- Export chapters to .txt format
- Modern, clean, professional SaaS-like interface

## Prerequisites

### Node.js Version
**No additional prerequisites needed!** FFmpeg is bundled with the Node.js version, so it works out of the box.

### Python Version (Original)
- Python 3.8+
- FFmpeg (required for MP3 to M4B conversion)

### Installing FFmpeg (Python Version Only)

**Windows:**
1. Go to https://www.gyan.dev/ffmpeg/builds/ (recommended Windows builds)
2. Download "ffmpeg-git-full.7z" or "ffmpeg-release-full.7z"
3. Extract the archive using 7-Zip or similar
4. Open the extracted folder, navigate to the `bin` folder
5. Copy the path to the `bin` folder (contains ffmpeg.exe)
6. Add to PATH:
   - Press Win + X, select "System"
   - Click "Advanced system settings"
   - Click "Environment Variables"
   - Under "System variables", find and select "Path", click "Edit"
   - Click "New" and paste the path to the `bin` folder
   - Click OK on all windows
7. Open a new command prompt and verify: `ffmpeg -version`

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install ffmpeg
```

**Note:** The Python version requires FFmpeg. The Node.js version includes FFmpeg automatically.

## Usage

### Web Interface

Start the web server and open your browser to http://localhost:5000:

```bash
# Start the server
bpm4b web

# Or with custom options
bpm4b web --port 8080
bpm4b web --host 127.0.0.1 --debug
```

The web interface allows you to:
- Upload MP3 files through a simple form
- Add custom chapter markers with titles and timestamps
- Download the converted M4B audiobook

### Command Line (No Web Interface)

Convert MP3 to M4B directly from the terminal:

```bash
# Basic conversion
bpm4b convert input.mp3 output.m4b

# With chapter markers
bpm4b convert input.mp3 output.m4b --chapter "Introduction" 0
bpm4b convert input.mp3 output.m4b --chapter "Chapter 1" 3600 --chapter "Chapter 2" 7200

# Multiple chapters
bpm4b convert book.mp3 book.m4b \\
  --chapter "Prologue" 0 \\
  --chapter "Chapter 1" 300 \\
  --chapter "Chapter 2" 1800

# Multiple chapters with MM:SS format
bpm4b convert book.mp3 book.m4b \\
 --chapter "Prologue" "0:00" \\
 --chapter "Chapter 1" "5:00" \\
 --chapter "Chapter 2" "30:00"

# Mixed formats (seconds and MM:SS)
bpm4b convert book.mp3 book.m4b \\
 --chapter "Intro" 0 \\
 --chapter "Chapter 1" "6:30" \\
 --chapter "Chapter 2" 3600
```

Chapter start times accept:
- Seconds as integer (e.g., `390`)
- Minutes:seconds format (e.g., `"6:30"` or `"6:30.5"` for fractional seconds)

### Using Python Module

Alternatively, you can run it as a Python module:

```bash
python -m bpm4b.cli web --port 5000
python -m bpm4b.cli convert input.mp3 output.m4b
```

### Using the CLI (Package Installation)

After installing with `pip install -e .`, use the `bpm4b` command:

```bash
# Start web interface
bpm4b web

# Web interface with options
bpm4b web --port 8080
bpm4b web --host 127.0.0.1 --debug

# Convert MP3 to M4B directly
bpm4b convert input.mp3 output.m4b
bpm4b convert input.mp3 output.m4b --chapter "Chapter 1" 0

# Show help
bpm4b --help
bpm4b web --help
bpm4b convert --help
```

### Using Python Module

Alternatively, you can run it as a Python module:

```bash
python -m bpm4b.cli web --port 5000
python -m bpm4b.cli convert input.mp3 output.m4b
```

### Using the Traditional Method

If you installed dependencies only (without the package):

```bash
python app.py
```

Then open your browser and navigate to:
```
http://localhost:5000
```

### Using the Tool

Once the server is running:

**MP3 to M4B**: Upload an MP3 file, add chapters using the automatic chapter builder, and click "Convert to M4B"
- Automatically converts to M4B format (iTunes/Apple Books compatible)
- Chapters automatically embedded with titles and timestamps
- Uses FFmpeg for high-quality AAC audio (64kbps - 256kbps)

**M4B to MP3**: Upload an M4B/M4A file and convert it to a standard MP3
- High-fidelity conversion using the libmp3lame encoder
- Perfect for playback on legacy devices or sharing

**Audiobook Gen**: Upload a PDF or Text document to generate a full audiobook
- Powered by Kokoro-82M Local TTS engine
- High-quality, human-like voice synthesis
- Automatic chapter detection and manifest generation

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

### POST /api/convert
Converts MP3 to M4B or M4B to MP3.

**Form Data:**
- `source_file`: The file to convert
- `output_name`: Custom filename
- `audio_quality`: Bitrate (e.g., '128k', '256k')
- `chapters` (optional): JSON array of chapter objects.

### POST /api/generate-audiobook
Generates an audiobook from a document.

**Form Data:**
- `doc_file`: The PDF or Text file
- `voice`: Selection from available Kokoro voices
- `output_name`: Custom filename

### GET /api/health
Health check endpoint. Returns JSON with status and FFmpeg availability.

**Response:**
Returns an M4B file as a download.

## Project Structure

### Python Version
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

### Node.js Version
```
.
├── bin/
│   └── bpm4b.js       # CLI entry point
├── lib/
│   ├── core.js        # Core conversion functions
│   └── server.js      # Express web server
├── templates/
│   └── index.ejs      # Frontend template
├── api/
│   └── index.js       # Vercel serverless function
├── examples/          # Usage examples
├── test/              # Unit tests
├── package.json       # NPM package configuration
├── vercel.json        # Vercel configuration
├── uploads/           # Temporary uploaded files (created automatically)
├── outputs/           # Generated files (created automatically)
└── README_NODE.md     # Node.js specific documentation
```

## Notes

- Maximum file size for uploads: 2GB
- SSE (Server-Sent Events) used for real-time progress updates
- Kokoro AI engine runs locally (no API keys or external costs)
- M4B output files can be large (typically 0.96-2GB per hour of audio depending on bitrate)
- Optimized for high-speed conversion on Windows/macOS/Linuxion:
- **X (Twitter)**: [@jdjchelp](https://x.com/jdjchelp)

## License

MIT