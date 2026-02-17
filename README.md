# Web & Audio Converter Tools

A Flask-based web application that provides two main features:
1. **Website to ZIP**: Download a website and convert it to a ZIP file
2. **MP3 to M4B**: Convert MP3 files to M4B audiobook format with chapter support

## Features

### Website to ZIP
- Enter any valid URL to download the website
- Recursively downloads pages from the same domain
- Preserves the website structure and assets
- Downloads as a compressed ZIP file

### MP3 to M4B Converter
- Upload MP3 files
- Add custom chapter markers with titles and timestamps
- Automatically converts to M4B format (iTunes/Apple Books compatible)
- Uses FFmpeg for high-quality audio conversion

## Prerequisites

- Python 3.8+
- FFmpeg (required for MP3 to M4B conversion)

### Installing FFmpeg

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

**Note:** The MP3 to M4B conversion requires FFmpeg. Without it, only the website to ZIP feature will work.

## Installation

1. Clone or download this repository
2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Start the Flask server:
```bash
python app.py
```

2. Open your browser and navigate to:
```
http://localhost:5000
```

3. Use the tools:
   - **Website to ZIP**: Enter a URL and click "Download & Create ZIP"
   - **MP3 to M4B**: Upload an MP3 file, optionally add chapters, and click "Convert to M4B"

## Vercel Deployment

This application can be deployed to Vercel as a serverless function:

1. Install Vercel CLI: `npm i -g vercel`
2. Run `vercel --prod` in the project directory
3. Vercel will automatically detect the Python project and deploy it

**Important Notes for Vercel:**
- The application uses `/tmp` directory for temporary file storage (Vercel's writable directory)
- Maximum execution time is 30 seconds (configurable in `vercel.json`)
- Memory limit is 1024MB (configurable in `vercel.json`)
- FFmpeg is NOT available on Vercel's serverless platform by default, so MP3 to M4B conversion will NOT work on Vercel
- The Website to ZIP feature will work on Vercel (doesn't require FFmpeg)
- For full functionality (including MP3 conversion), consider using a different hosting solution like a VPS or Railway

**Alternative for MP3 conversion on Vercel:**
You could use a separate FFmpeg server or service, but that would require significant architectural changes.

## API Endpoints

### POST /api/website-to-zip
Converts a website to a ZIP file.

**Request:**
```json
{
  "url": "https://example.com"
}
```

**Response:**
Returns a ZIP file as a download.

### POST /api/mp3-to-m4b
Converts an MP3 file to M4B with optional chapters.

**Form Data:**
- `mp3_file`: The MP3 file to convert
- `chapters` (optional): JSON array of chapter objects:
```json
[
  {"title": "Chapter 1", "start_time": 0},
  {"title": "Chapter 2", "start_time": 3600}
]
```

**Response:**
Returns an M4B file as a download.

## Project Structure

```
.
├── app.py              # Flask application (for local development)
├── api/
│   └── index.py       # Vercel serverless function
├── templates/
│   └── index.html     # Frontend interface
├── vercel.json         # Vercel configuration
├── requirements.txt    # Python dependencies
├── uploads/           # Temporary uploaded files (created automatically)
├── outputs/           # Generated files (created automatically)
└── README.md          # This file
```

## Notes

- The website downloader respects the same-origin policy and only follows links within the same domain
- Maximum file size for uploads: 100MB
- Website download limit: 50 pages per request
- Temporary files are cleaned up automatically
- M4B output files can be large (typically 0.96-2GB per hour of audio depending on bitrate)
- The default audio bitrate is 64kbps AAC, which provides good quality for speech

## License

MIT