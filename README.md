# BPM4B v13 — Ultimate Multimedia Processing Suite

<div align="center">

[![MIT License](https://img.shields.io/badge/License-MIT-22c55e?style=flat-square)](https://choosealicense.com/licenses/mit/)
[![PyPI Version](https://img.shields.io/pypi/v/bpm4b?style=flat-square&color=3776ab&logo=python&logoColor=white)](https://pypi.org/project/bpm4b/)
[![Python](https://img.shields.io/badge/Python-3.8+-339933?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-required-007808?style=flat-square&logo=ffmpeg)

**Convert MP3 ↔ M4B · Generate AI Audiobooks · Magic Preprocessing · Audio Splicing · Metadata & Cover Art**

```bash
pip install bpm4b
bpm4b web    # Start web interface at http://localhost:5000
```

</div>

---

## What's New in v13

| Version | Features |
|---------|----------|
| **v13** | ✨ **BPM4B Magic** (Roman numeral resolution + LitRPG stat block compaction) · **abogen integration** (replaces built-in TTS) · **Zero-copy audio splicing** · **M4B chapter demuxing** · **Binary cover art injector/extractor** · **Acoustic silence-based auto-chaptering** · **Smart border silence trimmer** · **Pre-flight storage estimator** · **Silence trimmer** · **Chunk-level MD5 caching** · **Dynamic concurrency throttle guard** · **SSE progress mirror** · **SQLite job history** · **CLI profile manager (.bpm4brc)** · **Cross-platform path portability** · **Intelligent FFmpeg discovery** · **Keyboard shortcuts in web UI** · **Multi-format chapter I/O (CUE/VTT/Audacity/CSV/JSON)** |
| **v12** | ⚡ Audio Format Converter (MP3/WAV/FLAC/AAC/OGG/ALAC) · Metadata Editor with Open Library Lookup · Document to EPUB · Audio Glue (Batch Merge) · Folder to M4B · EPUB to Audiobook · Health Check · SSE Progress Tracking |
| **v11** | ✍️ Interactive Pro Editor · Neural Narration Studio · Multi-voice dialogue |
| **v10** | 📚 M4B → MP3 · Document to Audiobook · Kokoro-82M TTS |

---

## Installation

### PyPI

```bash
pip install bpm4b
```

### TTS Support (optional — abogen)

```bash
pip install abogen
```

### All Extras

```bash
pip install bpm4b[all]
pip install abogen psutil mutagen
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

### CLI — Conversion

```bash
bpm4b convert input.mp3 output.m4b                              # MP3 → M4B
bpm4b convert input.mp3 output.m4b --quality 128k              # Custom quality
bpm4b convert input.m4b output.mp3                             # M4B → MP3
bpm4b demux audiobook.m4b ./chapters                           # Split M4B into chapter MP3s
```

### CLI — Audiobook Generation (with abogen)

```bash
bpm4b abogen book.pdf book.m4b                                 # PDF → audiobook
bpm4b abogen book.docx book.m4b --voice af_bella               # Custom voice
bpm4b abogen book.epub book.m4b --speed 1.25                   # Faster playback
```

### CLI — BPM4B Magic (Preprocessing)

```bash
bpm4b magic book.pdf magic_output.txt                          # Preprocess with defaults
bpm4b magic book.epub preview.json --preview                   # Preview chapters only
bpm4b magic book.pdf output.txt --no-roman                     # Skip Roman numeral resolution
bpm4b magic book.txt output.txt --stat-blocks skip             # Remove stat blocks entirely
```

### CLI — Audio Merge (Zero-Copy)

```bash
bpm4b audio-glue intro.mp3 chapter1.mp3 chapter2.mp3 book.m4b  # Fast stream copy
bpm4b audio-glue *.mp3 book.m4b --normalize                    # With normalization
```

### CLI — Silence & Trimming

```bash
bpm4b silence-chapter audio.mp3                                # Auto-detect chapters
bpm4b silence-chapter audio.mp3 --output chapters.json         # Save as JSON
bpm4b trim audio.mp3 --output trimmed.wav                      # Strip border silence
```

### CLI — Estimate & System

```bash
bpm4b estimate audio.mp3                                       # Pre-flight size estimate
bpm4b health                                                   # Check dependencies
bpm4b system                                                   # System resource info
bpm4b stats                                                    # Job history
bpm4b profile show                                             # Show config profile
bpm4b cache stats                                              # Cache statistics
```

### CLI — Cover Art

```bash
bpm4b cover extract book.m4b --output cover.jpg                # Extract cover
bpm4b cover inject book.m4b --cover cover.jpg                  # Inject cover
```

---

## Features

### 🔄 Audio Conversion
- MP3 ↔ M4B with embedded chapter markers
- M4B chapter demuxing (split into individual MP3 tracks)
- Audio Format Converter (MP3/WAV/FLAC/AAC/OGG/ALAC)
- Zero-copy audio splicing (stream copy mode, no re-encode)
- Batch merge with normalization

### 🎙️ AI Audiobook Generation
- Powered by **abogen** + BPM4B preprocessing
- Roman numeral resolution (Chapter IV → Chapter 4)
- LitRPG stat block compaction
- 10+ voices across US/UK English
- Automatic chapter detection from any document

### ✨ BPM4B Magic
- **Smart Roman Numeral Resolver** — context-aware detection (converts chapter/volume/book Roman numerals while preserving pronouns like "I")
- **LitRPG Stat Block Compactors** — detect repetitive stat tables and summarize or skip them
- **Chapter Title Normalization** — standardizes "Ch. I", "CHAPTER 2", "ch_03" → "Chapter 1/2/3"

### 🔇 Acoustic Processing
- Silence-based auto-chaptering (detects chapter breaks from audio silence)
- Border/all silence trimming (removes leading/trailing/all dead air)

### 🖼️ Cover Art & Metadata
- Binary cover art extractor/injector (stream-copy, no re-encode)
- Chapter atom syncing (M4B ↔ MP3)
- Metadata inheritance (reads first file's tags for batch conversions)
- Open Library metadata lookup

### 📊 Intelligence & Automation
- Intelligent FFmpeg path discovery (cross-platform auto-find)
- Dynamic concurrency throttle guard (auto-adjusts parallel workers)
- Pre-flight storage capacity estimator
- Conversion chunk-level caching (MD5 incremental)
- CLI profile manager (.bpm4brc config)
- SQLite-backed job history

### ⌨️ Web Interface
- Keyboard shortcuts (⌘1-9, ⌘B, ⌘O, ⌘T, ⌘/)
- Live SSE progress mirror
- 16 tool panels (convert, demux, magic, abogen, merge, silence, trim, cover, estimate, EPUB, metadata, jobs, system, shortcuts)
- Dark/light theme toggle

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/convert` | POST | Unified MP3↔M4B conversion |
| `/api/mp3-to-m4b` | POST | Explicit MP3 → M4B |
| `/api/generate-audiobook` | POST | Document to audiobook via abogen |
| `/api/audiobook` | POST | Full chapter-aware pipeline |
| `/api/magic` | POST | BPM4B preprocessing (Roman numerals + stat blocks) |
| `/api/epub-to-audiobook` | POST | EPUB to narrated audiobook |
| `/api/document-to-epub` | POST | Convert document to EPUB |
| `/api/convert-audio` | POST | Audio format conversion |
| `/api/audio-glue` | POST | Merge multiple audio files |
| `/api/demux` | POST | Split M4B into chapter MP3s |
| `/api/cover/extract` | POST | Extract cover art |
| `/api/cover/inject` | POST | Inject cover art |
| `/api/silence-chapter` | POST | Auto-detect chapters from silence |
| `/api/trim` | POST | Trim border silence |
| `/api/estimate` | POST | Pre-flight size estimate |
| `/api/metadata/extract` | POST | Extract metadata |
| `/api/metadata/apply` | POST | Apply metadata |
| `/api/metadata/lookup` | POST | Open Library lookup |
| `/api/preview-chapters` | POST | Preview chapter detection |
| `/api/chapters/import` | POST | Import chapters (CUE/VTT/CSV/JSON) |
| `/api/chapters/export` | POST | Export chapters |
| `/api/progress/stream` | GET | SSE progress stream |
| `/api/jobs` | GET | Job history |
| `/api/jobs/stats` | GET | Job statistics |
| `/api/profile` | GET/POST | Profile manager |
| `/api/system` | GET | System info |
| `/api/voices` | GET | List available TTS voices |
| `/api/health` | GET | System health check |
| `/api/cleanup` | POST | Clean old uploaded/output files |

---

## Requirements

- **Python 3.8+**
- **FFmpeg** (required for all audio operations)
- **abogen** (optional, for TTS/audiobook generation)

### Recommended

```bash
pip install psutil    # Accurate memory monitoring for concurrency guard
pip install mutagen   # ID3/MP4 tag reading
```

---

## Project Structure

```
bpm4b/
├── bpm4b/
│   ├── __init__.py              # Package metadata (v13.0.0)
│   ├── app.py                   # Flask web application (all endpoints)
│   ├── cli.py                   # Command-line interface (20+ commands)
│   ├── core.py                  # Core conversion functions
│   ├── path_utils.py            # Cross-platform path portability
│   ├── ffmpeg_utils.py          # FFmpeg discovery, silence detection, trim, estimators
│   ├── text_processor.py        # Roman numeral resolver & stat block compactors
│   ├── chapter_io.py            # Multi-format chapter import/export
│   ├── chapter_detector.py      # Chapter detection engine
│   ├── document_parser.py       # Document parsing (PDF/DOCX/EPUB/TXT)
│   ├── document_to_epub.py      # Document to EPUB converter
│   ├── audiobook_builder.py     # Legacy audiobook builder
│   ├── abogen_integration.py    # abogen TTS integration + BPM4B Magic
│   ├── splicer.py               # Zero-copy audio splicing & stream pipeline
│   ├── demuxer.py               # M4B chapter demuxing
│   ├── cache_manager.py         # MD5 chunk-level caching
│   ├── cover_art.py             # Cover art & chapter atom sync
│   ├── metadata.py              # Metadata extract/apply/lookup
│   ├── tts.py                   # Legacy TTS engine (Kokoro)
│   ├── sse_progress.py          # SSE progress management
│   ├── job_database.py          # SQLite job history
│   ├── profile_manager.py       # .bpm4brc config profiles
│   ├── concurrency_guard.py     # Dynamic worker throttling
│   └── templates/
│       └── index.html           # Web interface (keyboard shortcuts, SSE progress)
├── setup.py                     # Package configuration
├── pyproject.toml               # Build configuration
├── README.md                    # This file
├── test_text_processor.py       # Unit tests
├── test_chapter_io.py           # Unit tests
├── test_ffmpeg_utils.py         # Unit tests
├── test_cover_art.py            # Unit tests
└── test_v12_features.py         # Legacy test suite
```

---

## License

MIT License — see LICENSE file for details.

---

## Contact

- **X (Twitter):** [@jdjchelp](https://x.com/jdjchelp)
- **Issues:** https://github.com/jdjchelp-jpg/bpm4b/issues
