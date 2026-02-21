# MP3 to M4B Audiobook Converter (bpm4b)

A Flask-based web application for converting MP3 files to M4B audiobook format with chapter support.

**Install and run with:** `pip install -e .` then `bpm4b`

## Features

### MP3 to M4B Converter
- Upload MP3 files
- Add custom chapter markers with titles and timestamps
- Automatically converts to M4B format (iTunes/Apple Books compatible)
- Uses FFmpeg for high-quality AAC audio (64kbps)
- Simple web interface

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

**Note:** The MP3 to M4B conversion requires FFmpeg. Without it, the converter will not work.

## Installation

### Install from PyPI (for users)

Once published, anyone can install with:

```bash
pip install bpm4b
```

### Install from Source (for development)

```bash
# Clone or download this repository
cd htmltozip

# Install the package and its dependencies
pip install -e .
```

This installs the `bpm4b` command-line tool with all dependencies.

### Traditional Installation (without package)

```bash
# Clone or download this repository
cd htmltozip

# Install Python dependencies
pip install -r requirements.txt
```

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
```

Chapter start times are in seconds from the beginning of the audio.

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

**MP3 to M4B**: Upload an MP3 file, optionally add chapter markers, and click "Convert to M4B"
- Automatically converts to M4B format (iTunes/Apple Books compatible)
- Add custom chapter titles and timestamps
- Uses FFmpeg for high-quality AAC audio (64kbps)

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
- For full functionality, consider using a different hosting solution like a VPS or Railway

**Alternative for MP3 conversion on Vercel:**
You could use a separate FFmpeg server or service, but that would require significant architectural changes.

## Publishing to PyPI

### Step-by-Step Manual Publishing

Follow these exact steps to publish `bpm4b` to PyPI:

**1. Prepare Your Project**

Update `setup.py` with your information:
- `author`: Your name
- `author_email`: Your email
- `url`: Your GitHub repository URL

Make sure you're in the project directory:
```bash
cd c:/Users/johns/Downloads/htmltozip
```

**2. Create Accounts**

- Register at https://pypi.org (production)
- Register at https://test.pypi.org (for testing)

**3. Install Build Tools**

```bash
pip install --upgrade pip
pip install setuptools wheel twine
```

**4. Clean Previous Builds**

```bash
rm -rf dist build *.egg-info
# On Windows PowerShell:
# Remove-Item -Recurse -Force dist, build, *.egg-info
```

**5. Build the Package**

```bash
python setup.py sdist bdist_wheel
# Creates .tar.gz and .whl files in dist/
```

**6. Check Package Contents**

```bash
twine check dist/*
# Should show "Passed" for all files
```

**7. Test Upload to TestPyPI**

```bash
twine upload --repository testpypi dist/*
```

You'll be prompted for:
- Username: your TestPyPI username
- Password: your TestPyPI password (or API token)

**8. Test Install from TestPyPI**

```bash
# Create a fresh virtual environment (optional but recommended)
python -m venv test_env
test_env\Scripts\activate  # On Windows
# source test_env/bin/activate  # On macOS/Linux

# Install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ bpm4b

# Test it works
bpm4b --help
bpm4b web --help
bpm4b convert --help
```

**9. Upload to Production PyPI**

```bash
twine upload dist/*
```

Use your PyPI.org credentials.

**10. Verify Production Install**

```bash
# In a new terminal or after uninstalling test version
pip uninstall bpm4b -y
pip install bpm4b
bpm4b --help
```

**11. Tag Your Release**

```bash
git add .
git commit -m "Prepare for PyPI release"
git tag v1.0.0
git push origin v1.0.0
```

**12. Celebrate!** 🎉

Your package is now available at https://pypi.org/project/bpm4b/

Anyone can now install it with:
```bash
pip install bpm4b
```

### Automated Publishing with GitHub Actions

This project includes `.github/workflows/publish.yml` for automatic publishing.

**Setup (One-time):**

1. **Create PyPI Project**
   - Go to https://pypi.org/manage/projects/
   - Click "Add new project"
   - Name: `bpm4b`
   - Uncheck "Public" if you want private (usually keep public)
   - Create project

2. **Configure Trusted Publishing on PyPI**
   - Go to your project on PyPI
   - Click "Settings" → "Trusted publishers"
   - Click "Add publisher"
   - Choose "GitHub Actions"
   - Repository: `yourusername/bpm4b`
   - Workflow file: `.github/workflows/publish.yml`
   - Click "Add"
   - PyPI will show a "Client ID" - copy it

3. **Add GitHub Repository Settings**
   - Go to GitHub repo → Settings → Actions → General
   - Under "Workflow permissions", select **"Read and write permissions"**
   - Check "Allow GitHub Actions to create and approve pull requests"
   - Save

4. **Create GitHub Environment (Optional but Recommended)**
   - GitHub repo → Settings → Environments → New environment
   - Name: `pypi`
   - Add reviewers if desired
   - Save

**Usage:**

Push a version tag:
```bash
git tag v1.0.1
git push origin v1.0.1
```

The workflow will:
- Trigger on tag push
- Build the package
- Automatically publish to PyPI using OIDC (no secrets!)
- Show status in GitHub Actions tab

**Important:** Version numbers in `setup.py` must be incremented for each publish.

### Troubleshooting

**"File already exists" error:**
- Increment the version in `setup.py`
- Delete `dist/` folder and rebuild

**"Invalid long description" error:**
- Check README.md for broken markup
- Run `twine check dist/*` to see issues

**"403 Forbidden" from PyPI:**
- Verify username/password or API token
- For TestPyPI, use `--repository testpypi`
- Make sure you have rights to upload this package name

**Package not found after install:**
```bash
pip install bpm4b --no-cache-dir
```

**Windows-specific:**
- Use PowerShell or Git Bash for `rm -rf`
- Or manually delete `dist`, `build`, `*.egg-info` folders

## API Endpoints

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