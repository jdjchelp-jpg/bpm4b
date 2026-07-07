#!/usr/bin/env python3
"""
BPM4B CLI - Professional Multimedia Suite v12.0.0

Commands:
  web        Start web interface
  convert    MP3 to M4B or M4B to MP3
  audiobook  Document to M4B Audiobook
  epub       Document to EPUB
  audio-glue Merge multiple audio files
  health     Check system health
"""

import sys
import argparse
import os
import logging
from . import __version__
from .core import convert_mp3_to_m4b, convert_m4b_to_mp3, parse_time_to_seconds, check_ffmpeg


def web_command(args):
    """Start the web interface."""
    from .app import app
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║          BPM4B Professional Suite v{__version__}
║
║  Web interface starting...
║  URL: http://{'localhost' if args.host == '0.0.0.0' else args.host}:{args.port}
║  AI Engine: Kokoro-82M Local
║  Audio Converter · Metadata Editor · EPUB Tools
╚═══════════════════════════════════════════════════════════════╝
    """)
    app.run(host=args.host, port=args.port, debug=args.debug)


def convert_command(args):
    """Unified conversion command."""
    if not os.path.exists(args.input):
        print(f"Error: Input file '{args.input}' not found", file=sys.stderr)
        sys.exit(1)

    ext = os.path.splitext(args.input)[1].lower()
    is_mp3 = ext == '.mp3'

    print(f"[*] Processing: {args.input} -> {args.output}")

    try:
        if is_mp3:
            convert_mp3_to_m4b(args.input, args.output, args.chapters, quality=args.quality)
        else:
            convert_m4b_to_mp3(args.input, args.output, quality=args.quality)
        print(f"✓ Success: {args.output}")
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


def audiobook_command(args):
    """Generate audiobook from document."""
    try:
        if args.preview:
            from .audiobook_builder import preview_chapters
            print(f"\nAnalyzing document: {args.input}\n")
            preview = preview_chapters(args.input)
            print(f"Detected {len(preview['chapters'])} chapter(s):")
            print(f"Estimated duration: {preview['estimated_duration']}\n")
            for i, ch in enumerate(preview['chapters']):
                print(f"  {i + 1}. {ch['title']} ({ch['word_count']} words)")
                print(f"     Preview: {ch['preview'][:80]}...")
            print(f"\nTotal characters: {preview['total_characters']:,}")
            print(f"Generation time estimate — GPU: {preview['generation_time_estimate']['gpu']}"
                  f"  CPU: {preview['generation_time_estimate']['cpu']}")
            return

        from .audiobook_builder import build_audiobook
    except ImportError as e:
        print(f"Error: Missing dependency — {e}")
        print("Install TTS support: pip install kokoro>=0.9.4 soundfile")
        sys.exit(1)

    if not os.path.exists(args.input):
        print(f"Error: Input file '{args.input}' not found", file=sys.stderr)
        sys.exit(1)

    print(f"\nGenerating audiobook: {args.input} -> {args.output}")
    print(f"  Voice: {args.voice} | Speed: {args.speed} | Quality: {args.quality}\n")

    def on_progress(stage, detail):
        print(f"  [{stage}] {detail}")

    try:
        result = build_audiobook(args.input, args.output, {
            'voice': args.voice,
            'speed': args.speed,
            'audio_quality': args.quality,
            'on_progress': on_progress,
        })
        total = result['total_duration']
        print(f"\n✓ Audiobook ready: {args.output}")
        print(f"  Chapters: {len(result['chapters'])}")
        print(f"  Duration: {int(total // 60)}m {int(total % 60)}s")
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


def epub_command(args):
    """Convert document to EPUB format."""
    try:
        from .document_to_epub import convert_to_epub
    except ImportError as e:
        print(f"Error: Missing dependency — {e}")
        sys.exit(1)

    if not os.path.exists(args.input):
        print(f"Error: Input file '{args.input}' not found", file=sys.stderr)
        sys.exit(1)

    print(f"\nCreating EPUB: {args.input} -> {args.output}")
    print(f"  Title: {args.title or 'Auto'}")
    print(f"  Author: {args.author or 'Auto'}\n")

    try:
        result = convert_to_epub(args.input, args.output, {
            'title': args.title,
            'author': args.author,
            'language': args.language,
            'description': args.description,
        })
        print(f"✓ EPUB ready: {result['output_path']}")
        print(f"  Title: {result['title']}")
        print(f"  Author: {result['author']}")
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


def audio_glue_command(args):
    """Merge multiple audio files into one."""
    files = args.files
    if not files or len(files) < 2:
        print("Error: At least two input files required", file=sys.stderr)
        sys.exit(1)

    for f in files:
        if not os.path.exists(f):
            print(f"Error: File '{f}' not found", file=sys.stderr)
            sys.exit(1)

    print(f"\nMerging {len(files)} audio files -> {args.output}")
    if args.normalize:
        print("  Normalization: enabled")
    if args.volume != 1.0:
        print(f"  Volume: {args.volume}x")

    try:
        from .core import audio_glue
        audio_glue(files, args.output, normalize=args.normalize, volume=args.volume)
        print(f"✓ Merged audio: {args.output}")
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


def health_command(args):
    """Check system health and dependencies."""
    print(f"\nBPM4B v{__version__} — Health Check\n")

    ffmpeg = check_ffmpeg()
    print(f"  FFmpeg: {'✓ ' + ffmpeg.get('version', '') if ffmpeg.get('available') else '✗ Not found'}")

    # Check Python deps
    deps = [
        ('Flask', 'flask'),
        ('pypdf', 'pypdf'),
        ('mammoth', 'mammoth'),
        ('ebooklib', 'ebooklib'),
        ('beautifulsoup4', 'bs4'),
        ('soundfile', 'soundfile'),
        ('requests', 'requests'),
        ('kokoro (TTS)', 'kokoro'),
        ('kokoro-onnx (TTS)', 'kokoro_onnx'),
    ]
    for name, module_name in deps:
        try:
            __import__(module_name)
            print(f"  {name}: ✓")
        except ImportError:
            print(f"  {name}: ✗ Not installed")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="BPM4B - Professional Audio Suite v12",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  bpm4b web                          Start web interface
  bpm4b convert input.mp3 out.m4b    Convert MP3 to M4B
  bpm4b audiobook doc.pdf out.m4b    Generate audiobook from document
  bpm4b epub book.docx book.epub     Convert document to EPUB
  bpm4b audio-glue a.mp3 b.mp3 out.m4b  Merge audio files
  bpm4b health                       Check system health
        """
    )
    subparsers = parser.add_subparsers(dest='command')

    # Web
    web_p = subparsers.add_parser('web', help='Start web interface')
    web_p.add_argument('--host', default='0.0.0.0')
    web_p.add_argument('--port', type=int, default=5000)
    web_p.add_argument('--debug', action='store_true')

    # Convert
    conv_p = subparsers.add_parser('convert', help='MP3 to M4B or M4B to MP3')
    conv_p.add_argument('input')
    conv_p.add_argument('output')
    conv_p.add_argument('--quality', default='64k')
    conv_p.add_argument('--chapter', nargs=2, metavar=('TITLE', 'START'), action='append')

    # Audiobook
    audio_p = subparsers.add_parser('audiobook', help='Document to M4B Audiobook')
    audio_p.add_argument('input')
    audio_p.add_argument('output')
    audio_p.add_argument('--voice', default='af_heart')
    audio_p.add_argument('--speed', type=float, default=1.0)
    audio_p.add_argument('--quality', default='64k')
    audio_p.add_argument('--preview', action='store_true', help='Preview chapters without generating audio')

    # EPUB
    epub_p = subparsers.add_parser('epub', help='Convert document to EPUB')
    epub_p.add_argument('input')
    epub_p.add_argument('output')
    epub_p.add_argument('--title', default='', help='Book title')
    epub_p.add_argument('--author', default='', help='Book author')
    epub_p.add_argument('--language', default='en', help='Language code')
    epub_p.add_argument('--description', default='', help='Book description')

    # Audio Glue
    glue_p = subparsers.add_parser('audio-glue', help='Merge multiple audio files')
    glue_p.add_argument('files', nargs='+', help='Audio files to merge')
    glue_p.add_argument('output', help='Output merged file')
    glue_p.add_argument('--normalize', action='store_true', help='Normalize audio levels')
    glue_p.add_argument('--volume', type=float, default=1.0, help='Volume multiplier')

    # Health
    subparsers.add_parser('health', help='Check system health')

    args = parser.parse_args()

    if args.command == 'web':
        web_command(args)
    elif args.command == 'convert':
        if args.chapter:
            args.chapters = [{'title': c[0], 'start_time': c[1]} for c in args.chapter]
        else:
            args.chapters = None
        convert_command(args)
    elif args.command == 'audiobook':
        audiobook_command(args)
    elif args.command == 'epub':
        epub_command(args)
    elif args.command == 'audio-glue':
        audio_glue_command(args)
    elif args.command == 'health':
        health_command(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
