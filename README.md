# BPM4B v12 — Professional Multimedia Processing Suite

<div align="center">

[![MIT License](https://img.shields.io/badge/License-MIT-22c55e?style=flat-square)](https://choosealicense.com/licenses/mit/)
[![PyPI Version](https://img.shields.io/pypi/v/bpm4b?style=flat-square&color=3776ab&logo=python&logoColor=white)](https://pypi.org/project/bpm4b/)
[![Python](https://img.shields.io/badge/Python-3.8+-339933?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-required-007808?style=flat-square&logo=ffmpeg)

**Convert MP3 ↔ M4B · Generate AI Audiobooks · Process Documents to Audio · Create EPUBs · Edit Metadata**

```bash
pip install bpm4b
bpm4b web    # Start web interface at http://localhost:5000
```

</div>

---

## What's New in v12

| Version | Feature |
|---------|---------|
| **v12** | ⚡ Audio Format Converter (MP3/WAV/FLAC/AAC/OGG/ALAC) · Metadata Editor with Open Library Lookup · Document to EPUB · Audio Glue (Batch Merge) · Folder to M4B · EPUB to Audiobook · Health Check · SSE Progress Tracking |
| **v11** | ✍️ Interactive Pro Editor · Neural Narration Studio · Multi-voice dialogue |
| **v10** | 📚 M4B → MP3 · Document to Audiobook · Kokoro-82M TTS |

---

## Installation

### PyPI

```bash
pip install bpm4b
```

### TTS Support (optional)

```bash
# Standard Kokoro (recommended)
pip install bpm4b[tts]

# ONNX variant
pip install bpm4b[tts-onnx]

# All extras
pip install bpm4b[all]
```

### FFmpeg

FFmpeg is required and must be installed separately:

- **Windows:** Download from https://www.gyan.dev/ffmpeg/builds/ and add to PATH
- **macOS:** `brew install ffmpeg`
- **Linux:** `sudo apt-get install ffmpeg`

---

## Usage

### Web Interface

```bash
bpm4b web                        # Start at http://localhost:5000
bpm4b web --port 8080            # Custom port
bpm4b web --host 127.0.0.1       # Custom host
```

### CLI — MP3 ↔ M4B

```bash
bpm4b convert input.mp3 output.m4b                              # Basic
bpm4b convert input.mp3 output.m4b --quality 128k              # Custom quality
bpm4b convert input.mp3 output.m4b --chapter "Intro" 0 --chapter "Ch1" 300  # With chapters
bpm4b convert input.m4b output.mp3                             # M4B to MP3
```

### CLI — Audiobook Generation

```bash
bpm4b audiobook book.pdf book.m4b                             # PDF to audiobook
bpm4b audiobook book.docx book.m4b --voice af_bella           # Custom voice
bpm4b audiobook book.epub book.m4b --speed 1.25               # Faster playback
bpm4b audiobook book.txt book.m4b --preview                   # Preview chapters only
```

### CLI — EPUB Creation

```bash
bpm4b epub book.pdf book.epub                                 # PDF to EPUB
bpm4b epub book.docx book.epub --title "My Book" --author "Me"  # With metadata
bpm4b epub index.html book.epub                               # HTML to EPUB
```

### CLI — Audio Merge (Glue)

```bash
bpm4b audio-glue intro.mp3 chapter1.mp3 chapter2.mp3 book.m4b   # Merge files
bpm4b audio-glue *.mp3 book.m4b --normalize                    # With normalization
bpm4b audio-glue a.mp3 b.mp3 out.m4b --volume 1.5             # Boost volume
```

### CLI — Health Check

```bash
bpm4b health
```

---

## Features

### 🔄 MP3 ↔ M4B Conversion
- MP3 → M4B with embedded chapter markers
- M4B → MP3 high-fidelity extraction
- Custom audio quality (64k–256k)
- Chapter timestamps in seconds or MM:SS format

### 🎙️ AI Audiobook Generation
- Powered by **Kokoro-82M** Local TTS engine (no API key needed)
- 50+ voices across 9 languages
- Adjustable speed (0.5x–2.0x)
- Automatic chapter detection
- Support for PDF, DOCX, TXT, EPUB, MD

### 🔊 Audio Format Converter
- Convert between MP3, WAV, FLAC, AAC, OGG, ALAC
- Configurable bitrate and quality settings
- Lossless options for FLAC and WAV

### 📖 Document to EPUB
- Convert PDF, DOCX, TXT, MD, HTML, RTF to EPUB
- Automatic chapter detection and splitting
- Custom metadata (title, author, language)
- Styled XHTML output with CSS

### 🏷️ Metadata Editor
- Extract metadata from M4B/M4A files
- Edit title, author, genre, description
- Embed cover art
- Lookup metadata from **Open Library**

### 🔀 Batch Merge (Audio Glue)
- Merge multiple audio files into one
- Optional loudness normalization
- Volume adjustment
- Seamless gapless concatenation

### 📁 Folder to M4B
- Batch convert entire folders of audio files
- Auto-generated chapter markers from filenames
- Parallel processing support

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/convert` | POST | Unified MP3↔M4B conversion |
| `/api/mp3-to-m4b` | POST | Explicit MP3 → M4B |
| `/api/generate-audiobook` | POST | Document to audiobook via TTS |
| `/api/audiobook` | POST | Full chapter-aware audiobook pipeline |
| `/api/epub-to-audiobook` | POST | EPUB to narrated audiobook |
| `/api/document-to-epub` | POST | Convert document to EPUB |
| `/api/convert-audio` | POST | Audio format conversion |
| `/api/audio-glue` | POST | Merge multiple audio files |
| `/api/metadata/extract` | POST | Extract metadata from M4B/M4A |
| `/api/metadata/apply` | POST | Apply metadata to M4B/M4A |
| `/api/metadata/lookup` | POST | Lookup metadata from Open Library |
| `/api/preview-chapters` | POST | Preview chapter detection |
| `/api/voices` | GET | List available TTS voices |
| `/api/health` | GET | System health check |
| `/api/cleanup` | POST | Clean old uploaded/output files |

---

## Requirements

- **Python 3.8+**
- **FFmpeg** (required for all audio operations)
- **Kokoro** (optional, for TTS/audiobook generation)

---

## Project Structure

```
bpm4b/
├── bpm4b/
│   ├── __init__.py          # Package metadata (v12.0.0)
│   ├── app.py               # Flask web application (all endpoints)
│   ├── cli.py               # Command-line interface
│   ├── core.py              # Core conversion functions
│   ├── audiobook_builder.py # Full audiobook pipeline
│   ├── chapter_detector.py  # Chapter detection engine
│   ├── document_parser.py   # Document parsing (PDF/DOCX/EPUB/TXT)
│   ├── document_to_epub.py  # Document to EPUB converter
│   ├── metadata.py          # Metadata extract/apply/lookup
│   ├── tts.py               # TTS engine (Kokoro)
│   └── templates/
│       └── index.html       # Web interface
├── setup.py                 # Package configuration
├── pyproject.toml           # Build configuration
└── README.md                # This file
```

---

## License

MIT License — see LICENSE file for details.

---

## Contact

- **X (Twitter):** [@jdjchelp](https://x.com/jdjchelp)
- **Issues:** https://github.com/jdjchelp-jpg/bpm4b/issues
