#!/usr/bin/env python3
"""
BPM4B CLI - Ultimate Multimedia Suite v13

Commands:
  web              Start web interface
  convert          MP3 to M4B or M4B to MP3
  audiobook        Document to M4B Audiobook (legacy — use abogen)
  magic            Preprocess document with Roman numeral & stat block magic
  abogen           Generate audiobook using abogen (with BPM4B preprocessing)
  epub             Document to EPUB
  audio-glue       Merge multiple audio files
  health           Check system health
  profile          Manage processing profiles (.bpm4brc)
  cache            Manage conversion cache
  demux            Split M4B into chapter MP3s
  silence-chapter  Auto-detect chapters from silence regions
  estimate         Estimate output size before conversion
  trim             Trim border silence from audio
  stats            Show job history statistics
  cover            Extract or inject cover art
  system           Show system resource information
"""

import sys
import argparse
import os
import logging
import json
from . import __version__
from .core import convert_mp3_to_m4b, convert_m4b_to_mp3, parse_time_to_seconds, check_ffmpeg


def web_command(args):
    """Start the web interface."""
    from .app import app
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║          BPM4B Ultimate Suite v{__version__}
║
║  Web interface starting...
║  URL: http://{'localhost' if args.host == '0.0.0.0' else args.host}:{args.port}
║  AI Engine: abogen + Kokoro-82M Local
║  Audio Converter · Metadata Editor · EPUB Tools
║  SSE Progress · Keyboard Shortcuts · Job History
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


def magic_command(args):
    """Preprocess a document with BPM4B magic (Roman numeral resolution, stat block compaction)."""
    from .abogen_integration import bpm4b_magic, preprocess_for_abogen

    if not os.path.exists(args.input):
        print(f"Error: Input file '{args.input}' not found", file=sys.stderr)
        sys.exit(1)

    options = {
        'resolve_roman': not args.no_roman,
        'stat_block_mode': args.stat_blocks,
        'mode': 'ordinal',
    }

    print(f"\n✨ BPM4B Magic v{__version__}")
    print(f"   Input: {args.input}")
    print(f"   Roman numeral resolution: {'on' if options['resolve_roman'] else 'off'}")
    print(f"   Stat block mode: {options['stat_block_mode']}")
    print()

    try:
        if args.preview:
            result = preprocess_for_abogen(args.input, options)
            print(f"📖 Document Analysis:")
            print(f"   Chapters detected: {result['chapter_count']}")
            print(f"   Total characters: {result['total_chars']:,}")
            print(f"   Stat blocks found: {result.get('stat_blocks_found', 0)}")
            print(f"\n📑 Chapter List:")
            for i, ch in enumerate(result['chapters']):
                preview = ch.get('content', '')[:60].replace('\n', ' ')
                print(f"   {i + 1}. {ch['title']} — \"{preview}...\"")
            return

        result = bpm4b_magic(args.input, args.output, options)
        print(f"✓ Magic complete!")
        print(f"  Chapters: {result['chapter_count']} | "
              f"Chars: {result['total_chars']:,} | "
              f"Stat blocks: {result.get('stat_blocks_found', 0)}")
        print(f"  Output: {args.output}")

    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


def abogen_command(args):
    """Generate audiobook using abogen (with BPM4B preprocessing)."""
    from .abogen_integration import run_abogen, is_abogen_available

    if not is_abogen_available():
        print("Error: abogen not found. Install it:", file=sys.stderr)
        print("  pip install abogen", file=sys.stderr)
        print("  OR: https://github.com/denizsafak/abogen", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.input):
        print(f"Error: Input file '{args.input}' not found", file=sys.stderr)
        sys.exit(1)

    options = {
        'voice': args.voice,
        'speed': args.speed,
        'format': args.format,
        'preprocess': not args.no_preprocess,
        'resolve_roman': not args.no_roman,
        'stat_block_mode': args.stat_blocks,
    }

    print(f"\n🎧 BPM4B + abogen Audiobook Generation")
    print(f"   Input: {args.input} -> {args.output}")
    print(f"   Voice: {args.voice} | Speed: {args.speed}x")
    print(f"   Preprocessing: {'on' if options['preprocess'] else 'off'}")
    print()

    def on_progress(stage, detail):
        print(f"  [{stage}] {detail}")

    try:
        result = run_abogen(args.input, args.output, options, on_progress)
        print(f"\n✓ Audiobook ready: {args.output}")
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


def audiobook_command(args):
    """Legacy audiobook command — delegates to abogen."""
    print("⚠️  The built-in audiobook generator has been replaced by abogen.")
    print("   Running: bpm4b abogen with the same arguments...\n")
    # Build abogen-compatible args and call abogen_command directly
    from argparse import Namespace
    abogen_args = Namespace(
        input=args.input,
        output=args.output,
        voice=args.voice,
        speed=args.speed,
        format='m4b',
        no_preprocess=False,
        no_roman=False,
        stat_blocks='summarize',
    )
    abogen_command(abogen_args)


def epub_command(args):
    """Convert document to EPUB format."""
    try:
        from .document_to_epub import convert_to_epub
    except ImportError as e:
        print(f"Error: Missing dependency — {e}", file=sys.stderr)
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
    """Merge multiple audio files into one (zero-copy by default)."""
    files = args.files
    if not files or len(files) < 2:
        print("Error: At least two input files required", file=sys.stderr)
        sys.exit(1)

    for f in files:
        if not os.path.exists(f):
            print(f"Error: File '{f}' not found", file=sys.stderr)
            sys.exit(1)

    print(f"\nMerging {len(files)} audio files -> {args.output}")
    if args.stream_copy:
        print("  Mode: Zero-copy stream copy (fast, lossless)")
    else:
        print("  Mode: Re-encode")
    if args.normalize:
        print("  Normalization: enabled")
    if args.volume != 1.0:
        print(f"  Volume: {args.volume}x")

    try:
        from .splicer import splice_audio_files
        result = splice_audio_files(
            files, args.output,
            stream_copy=args.stream_copy,
            normalize=args.normalize,
            volume=args.volume,
        )
        print(f"✓ Merged audio: {args.output}")
        print(f"  Duration: {result.get('total_duration', 0):.1f}s")
        print(f"  Stream copy: {'yes' if result.get('stream_copy_used') else 'no'}")
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


def health_command(args):
    """Check system health and dependencies."""
    from .ffmpeg_utils import get_ffmpeg_info, check_ffmpeg_compat
    from .abogen_integration import is_abogen_available
    from .concurrency_guard import get_system_summary
    from .profile_manager import find_rc_file

    print(f"\nBPM4B v{__version__} — Health Check\n")

    # FFmpeg
    ffmpeg = get_ffmpeg_info()
    if ffmpeg['available']:
        print(f"  FFmpeg: ✓ {ffmpeg.get('version', '')[:80]}")
        print(f"    Path: {ffmpeg.get('path', 'N/A')}")
    else:
        print(f"  FFmpeg: ✗ Not found")

    # FFmpeg compat
    compat = check_ffmpeg_compat()
    if compat['available']:
        for feat, ok in compat.items():
            if feat != 'available':
                print(f"    {feat}: {'✓' if ok else '✗'}")

    # Abogen
    print(f"  abogen: {'✓ Available' if is_abogen_available() else '✗ Not installed'}")

    # Config profile
    rc = find_rc_file()
    print(f"  Config: {'✓ ' + rc if rc else '— None found'}")

    # System
    sys_info = get_system_summary()
    print(f"\n  System: {sys_info.get('cpu_cores', '?')} cores")
    print(f"    Memory: {sys_info.get('available_memory', '?')} avail / {sys_info.get('total_memory', '?')} total")
    print(f"    Recommended concurrency: {sys_info.get('recommended_concurrency', '?')}")
    if not sys_info.get('psutil_available'):
        print(f"    ⚠ psutil not installed — memory detection limited (pip install psutil)")

    # Python deps
    print(f"\n  Python Dependencies:")
    deps = [
        ('Flask', 'flask'),
        ('pypdf', 'pypdf'),
        ('mammoth', 'mammoth'),
        ('ebooklib', 'ebooklib'),
        ('beautifulsoup4', 'bs4'),
        ('soundfile', 'soundfile'),
        ('requests', 'requests'),
        ('psutil (recommended)', 'psutil'),
        ('mutagen (cover art)', 'mutagen'),
    ]
    for name, module_name in deps:
        try:
            __import__(module_name)
            print(f"    {name}: ✓")
        except ImportError:
            print(f"    {name}: ✗ Not installed")

    print()


def profile_command(args):
    """Manage processing profiles."""
    from .profile_manager import (
        load_profile, save_profile, list_saved_profiles,
        create_default_profile, find_rc_file
    )

    if args.action == 'list':
        profiles = list_saved_profiles()
        if not profiles:
            print("No profiles found.")
            return
        print(f"\n📋 Found {len(profiles)} profile(s):\n")
        for p in profiles:
            print(f"  {p['filename']}")
            print(f"    Path: {p['path']}")
            print(f"    Size: {p['size']} bytes")
            print()

    elif args.action == 'show':
        config = load_profile(args.file)
        print(json.dumps(config, indent=2))

    elif args.action == 'create':
        if not args.file:
            args.file = os.path.join(os.getcwd(), '.bpm4brc')
        if os.path.exists(args.file):
            print(f"File already exists: {args.file}")
            return
        create_default_profile(args.file)
        print(f"✓ Created default profile: {args.file}")

    elif args.action == 'apply':
        config = load_profile(args.file)
        print(f"✓ Applied profile: {args.file}")
        # Print effective config
        for section, values in config.items():
            if isinstance(values, dict):
                print(f"\n  [{section}]")
                for k, v in values.items():
                    if v:
                        print(f"    {k} = {v}")

    else:
        print(f"Unknown profile action: {args.action}")


def cache_command(args):
    """Manage the conversion cache."""
    from .cache_manager import get_cache

    cache = get_cache()

    if args.action == 'stats':
        stats = cache.get_stats()
        print(f"\n📦 Cache Statistics:")
        print(f"  Total entries: {stats['total_entries']}")
        print(f"  Unique sources: {stats['unique_sources']}")
        print(f"  Cache file: {stats['cache_path']}")
        print(f"  Index size: {stats['cache_size_bytes']:,} bytes")

    elif args.action == 'clear':
        cache.clear()
        print("✓ Cache cleared")

    elif args.action == 'invalidate':
        if args.file:
            for f in args.file:
                if cache.invalidate(f):
                    print(f"  Invalidated: {f}")
                else:
                    print(f"  Not cached: {f}")

    else:
        print(f"Unknown cache action: {args.action}")


def demux_command(args):
    """Split M4B into individual MP3 chapter tracks."""
    from .demuxer import demux_m4b_to_mp3

    if not os.path.exists(args.input):
        print(f"Error: File '{args.input}' not found", file=sys.stderr)
        sys.exit(1)

    output_dir = args.output or os.path.splitext(args.input)[0] + '_chapters'
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n🔊 Demuxing M4B to MP3 chapters")
    print(f"   Input: {args.input}")
    print(f"   Output: {output_dir}/")
    print(f"   Quality: {args.quality}\n")

    try:
        results = demux_m4b_to_mp3(args.input, output_dir, quality=args.quality)
        print(f"✓ Extracted {len(results)} chapter(s):\n")
        for r in results:
            size = os.path.getsize(r['output_path']) if r.get('output_path') and os.path.exists(r['output_path']) else 0
            size_str = f"{size / 1024:.0f} KB" if size else "Error"
            print(f"  {os.path.basename(r['output_path'])}  ({r['duration']:.1f}s, {size_str})")
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


def silence_chapter_command(args):
    """Auto-detect chapters from silence regions."""
    from .ffmpeg_utils import auto_chapter_from_silence, get_audio_duration

    if not os.path.exists(args.input):
        print(f"Error: File '{args.input}' not found", file=sys.stderr)
        sys.exit(1)

    print(f"\n🔇 Acoustic Silence-Based Auto-Chaptering")
    print(f"   Input: {args.input}")
    print(f"   Noise threshold: {args.threshold}")
    print(f"   Min silence: {args.min_silence}s")
    print(f"   Min chapter: {args.min_chapter}s\n")

    try:
        chapters = auto_chapter_from_silence(
            args.input,
            noise_threshold=args.threshold,
            min_silence_duration=args.min_silence,
            min_chapter_duration=args.min_chapter,
        )

        print(f"✓ Detected {len(chapters)} chapter(s):\n")
        for i, ch in enumerate(chapters):
            print(f"  {i + 1}. {ch['title']}  ({ch['start_time']:.1f}s — {ch['end_time']:.1f}s)")

        if args.output:
            ext = os.path.splitext(args.output)[1].lower()
            if ext == '.json':
                with open(args.output, 'w') as f:
                    json.dump(chapters, f, indent=2)
            else:
                from .chapter_io import export_chapters
                fmt_map = {'.vtt': 'vtt', '.cue': 'cue', '.csv': 'csv'}
                export_chapters(chapters, args.output, format=fmt_map.get(ext, 'chapters.txt'))
            print(f"\n✓ Saved chapters to: {args.output}")

    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


def estimate_command(args):
    """Estimate output size before conversion."""
    from .ffmpeg_utils import estimate_output_size, estimate_batch_output_size

    files = args.files
    if not files:
        print("Error: No files provided", file=sys.stderr)
        sys.exit(1)

    for f in files:
        if not os.path.exists(f):
            print(f"Error: File '{f}' not found", file=sys.stderr)
            sys.exit(1)

    print(f"\n📊 Pre-Flight Storage Estimator")
    print(f"   Target bitrate: {args.bitrate}kbps")
    print(f"   Output format: {args.format}\n")

    if len(files) == 1:
        est = estimate_output_size(files[0], args.bitrate, args.format)
        print(f"  Input: {os.path.basename(est['input_path'])}")
        print(f"  Duration: {est.get('duration_human', 'Unknown')}")
        print(f"  Estimated size: {est.get('estimated_size_human', 'Unknown')}")
        if est.get('warning'):
            print(f"\n  ⚠ {est['warning']}")
    else:
        est = estimate_batch_output_size(files, args.bitrate, args.format)
        print(f"  Total files: {len(est['files'])}")
        print(f"  Total duration: {est['total_duration_human']}")
        print(f"  Estimated total size: {est['total_estimated_size_human']}")
        print(f"\n  Per file:")
        for f_est in est['files']:
            print(f"    {os.path.basename(f_est['input_path'])}: "
                  f"{f_est.get('duration_human', '?')} → "
                  f"{f_est.get('estimated_size_human', '?')}")
        if est.get('warning'):
            print(f"\n  ⚠ {est['warning']}")


def trim_command(args):
    """Trim border silence from audio files."""
    from .ffmpeg_utils import trim_border_silence, trim_all_silence

    if not os.path.exists(args.input):
        print(f"Error: File '{args.input}' not found", file=sys.stderr)
        sys.exit(1)

    output = args.output or args.input.replace('.', '_trimmed.')
    if output == args.input:
        base, ext = os.path.splitext(args.input)
        output = f"{base}_trimmed{ext}"

    print(f"\n✂️  Border Silence Trimmer")
    print(f"   Input: {args.input}")
    print(f"   Output: {output}")
    print(f"   Mode: {'all' if args.all else 'borders'}")
    print(f"   Threshold: {args.threshold}")
    print(f"   Min silence: {args.min_silence}s\n")

    try:
        if args.all:
            trim_all_silence(args.input, output, args.threshold, args.min_silence)
        else:
            trim_border_silence(args.input, output, args.threshold, args.min_silence)
        print(f"✓ Trimmed audio: {output}")
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


def stats_command(args):
    """Show job history statistics."""
    from .job_database import get_db

    db = get_db()
    stats = db.get_stats()

    if args.action == 'list':
        jobs = db.list_jobs(limit=args.limit)
        if not jobs:
            print("No job history found.")
            return
        print(f"\n📋 Recent Jobs ({len(jobs)}):\n")
        for j in jobs:
            status_icon = {'complete': '✓', 'error': '✗', 'running': '🔄'}.get(j.get('status', ''), '?')
            created = j.get('created_at_iso', '?')[:19]
            job_type = j.get('job_type', '?')
            source = j.get('source_name', '?')
            print(f"  {status_icon} [{created}] {job_type}: {source}")

    elif args.action == 'clear':
        count = db.clear_history()
        print(f"✓ Cleared {count} job(s) from history")

    else:
        # Default: show stats
        print(f"\n📊 Job History Statistics:")
        print(f"  Total jobs: {stats.get('total_jobs', 0)}")
        print(f"  Completed: {stats.get('completed', 0)}")
        print(f"  Failed: {stats.get('failed', 0)}")
        print(f"  Running: {stats.get('running', 0)}")
        print(f"  Total duration: {stats.get('total_duration_seconds', 0):.0f}s")
        print(f"  Total files processed: {stats.get('total_files_processed', 0)}")
        if stats.get('jobs_by_type'):
            print(f"\n  By type:")
            for jt, count in stats['jobs_by_type'].items():
                print(f"    {jt}: {count}")


def cover_command(args):
    """Extract or inject cover art."""
    from .cover_art import extract_cover_art, inject_cover_art, inject_cover_from_base64
    import base64

    if args.action == 'extract':
        if not os.path.exists(args.input):
            print(f"Error: File '{args.input}' not found", file=sys.stderr)
            sys.exit(1)
        output = args.output or os.path.splitext(args.input)[0] + '_cover.jpg'
        print(f"\n🖼️ Extracting cover art...")
        data = extract_cover_art(args.input, output)
        if data:
            print(f"✓ Cover art saved: {output} ({len(data):,} bytes)")
        else:
            print("No cover art found in file.")

    elif args.action == 'inject':
        if not os.path.exists(args.input):
            print(f"Error: File '{args.input}' not found", file=sys.stderr)
            sys.exit(1)
        if not os.path.exists(args.cover):
            print(f"Error: Cover image '{args.cover}' not found", file=sys.stderr)
            sys.exit(1)
        output = args.output or args.input.replace('.', '_with_cover.')
        print(f"\n🖼️ Injecting cover art...")
        inject_cover_art(args.input, args.cover, output)
        print(f"✓ Cover injected: {output}")

    else:
        print(f"Unknown cover action: {args.action}. Use 'extract' or 'inject'.")


def system_command(args):
    """Show system resource information."""
    from .concurrency_guard import get_system_summary, get_memory_usage_pct
    from .ffmpeg_utils import get_ffmpeg_info
    import platform

    sys_info = get_system_summary()
    ffmpeg = get_ffmpeg_info()

    print(f"\n💻 System Information:")
    print(f"  Platform: {platform.system()} {platform.release()}")
    print(f"  Python: {platform.python_version()}")
    print(f"  CPU cores: {sys_info.get('cpu_cores', '?')}")
    print(f"  Memory: {sys_info.get('available_memory', '?')} avail / "
          f"{sys_info.get('total_memory', '?')} total")
    print(f"  Memory usage: {get_memory_usage_pct():.0f}%")
    print(f"  Recommended concurrency: {sys_info.get('recommended_concurrency', '?')}")
    print(f"  psutil: {'✓' if sys_info.get('psutil_available') else '✗ (pip install psutil)'}")
    print(f"  FFmpeg: {'✓' if ffmpeg.get('available') else '✗'}")
    if ffmpeg.get('path'):
        print(f"    Path: {ffmpeg['path']}")


def main():
    parser = argparse.ArgumentParser(
        description=f"BPM4B - Ultimate Audio Suite v{__version__}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  bpm4b web                          Start web interface
  bpm4b convert input.mp3 out.m4b    Convert MP3 to M4B
  bpm4b magic doc.pdf magic.txt      Preprocess document
  bpm4b abogen doc.pdf out.m4b       Generate audiobook via abogen
  bpm4b epub book.docx book.epub     Convert document to EPUB
  bpm4b audio-glue a.mp3 b.mp3 out.m4b  Zero-copy merge
  bpm4b demux audiobook.m4b ./chapters  Split M4B into MP3s
  bpm4b silence-chapter audio.mp3    Auto-detect chapters
  bpm4b estimate audio.mp3           Estimate output size
  bpm4b trim audio.mp3               Trim silence borders
  bpm4b cover extract audio.m4b      Extract cover art
  bpm4b profile show                 Show config profile
  bpm4b stats                        Show job history
  bpm4b health                       Check system health
  bpm4b system                       Show system info
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

    # Audiobook (legacy — redirects to abogen)
    audio_p = subparsers.add_parser('audiobook', help='Document to M4B Audiobook (legacy, uses abogen)')
    audio_p.add_argument('input')
    audio_p.add_argument('output')
    audio_p.add_argument('--voice', default='af_heart')
    audio_p.add_argument('--speed', type=float, default=1.0)
    audio_p.add_argument('--quality', default='64k')
    audio_p.add_argument('--preview', action='store_true', help='Preview chapters without generating audio')

    # BPM4B Magic
    magic_p = subparsers.add_parser('magic', help='Preprocess document with Roman numeral & stat block magic')
    magic_p.add_argument('input')
    magic_p.add_argument('output', nargs='?', default='')
    magic_p.add_argument('--no-roman', action='store_true', help='Disable Roman numeral resolution')
    magic_p.add_argument('--stat-blocks', choices=['summarize', 'skip', 'keep', 'flag'],
                        default='summarize', help='Stat block handling mode')
    magic_p.add_argument('--preview', action='store_true', help='Preview detected chapters without output')

    # Abogen
    abogen_p = subparsers.add_parser('abogen', help='Generate audiobook using abogen (with BPM4B preprocessing)')
    abogen_p.add_argument('input')
    abogen_p.add_argument('output')
    abogen_p.add_argument('--voice', default='af_heart')
    abogen_p.add_argument('--speed', type=float, default=1.0)
    abogen_p.add_argument('--format', choices=['m4b', 'mp3', 'wav', 'flac'], default='m4b')
    abogen_p.add_argument('--no-preprocess', action='store_true', help='Skip BPM4B preprocessing')
    abogen_p.add_argument('--no-roman', action='store_true', help='Disable Roman numeral resolution')
    abogen_p.add_argument('--stat-blocks', choices=['summarize', 'skip', 'keep', 'flag'],
                        default='summarize', help='Stat block handling mode')

    # EPUB
    epub_p = subparsers.add_parser('epub', help='Convert document to EPUB')
    epub_p.add_argument('input')
    epub_p.add_argument('output')
    epub_p.add_argument('--title', default='', help='Book title')
    epub_p.add_argument('--author', default='', help='Book author')
    epub_p.add_argument('--language', default='en', help='Language code')
    epub_p.add_argument('--description', default='', help='Book description')

    # Audio Glue
    glue_p = subparsers.add_parser('audio-glue', help='Merge multiple audio files (zero-copy by default)')
    glue_p.add_argument('files', nargs='+', help='Audio files to merge')
    glue_p.add_argument('output', help='Output merged file')
    glue_p.add_argument('--normalize', action='store_true', help='Normalize audio levels')
    glue_p.add_argument('--volume', type=float, default=1.0, help='Volume multiplier')
    glue_p.add_argument('--no-stream-copy', dest='stream_copy', action='store_false',
                       help='Re-encode instead of stream copy')
    glue_p.set_defaults(stream_copy=True)

    # Health
    subparsers.add_parser('health', help='Check system health')

    # Profile
    profile_p = subparsers.add_parser('profile', help='Manage processing profiles')
    profile_p.add_argument('action', choices=['list', 'show', 'create', 'apply'])
    profile_p.add_argument('--file', '-f', default='', help='Profile file path')

    # Cache
    cache_p = subparsers.add_parser('cache', help='Manage conversion cache')
    cache_p.add_argument('action', choices=['stats', 'clear', 'invalidate'])
    cache_p.add_argument('--file', '-f', nargs='+', help='Files to invalidate')

    # Demux
    demux_p = subparsers.add_parser('demux', help='Split M4B into chapter MP3s')
    demux_p.add_argument('input')
    demux_p.add_argument('output', nargs='?', default='', help='Output directory')
    demux_p.add_argument('--quality', default='128k')

    # Silence Chapter
    sc_p = subparsers.add_parser('silence-chapter', help='Auto-detect chapters from silence')
    sc_p.add_argument('input')
    sc_p.add_argument('--output', '-o', default='', help='Save chapters to file')
    sc_p.add_argument('--threshold', default='-30dB', help='Noise threshold (e.g., -30dB)')
    sc_p.add_argument('--min-silence', type=float, default=2.0, help='Min silence duration (s)')
    sc_p.add_argument('--min-chapter', type=float, default=60.0, help='Min chapter duration (s)')

    # Estimate
    est_p = subparsers.add_parser('estimate', help='Estimate output size before conversion')
    est_p.add_argument('files', nargs='+', help='Audio files')
    est_p.add_argument('--bitrate', type=int, default=64, help='Target bitrate in kbps')
    est_p.add_argument('--format', default='m4b', help='Output format')

    # Trim
    trim_p = subparsers.add_parser('trim', help='Trim border silence from audio')
    trim_p.add_argument('input')
    trim_p.add_argument('--output', '-o', default='', help='Output path')
    trim_p.add_argument('--all', action='store_true', help='Remove ALL silence (not just borders)')
    trim_p.add_argument('--threshold', default='-50dB', help='Noise threshold')
    trim_p.add_argument('--min-silence', type=float, default=0.1, help='Min silence to remove (s)')

    # Stats
    stats_p = subparsers.add_parser('stats', help='Show job history statistics')
    stats_p.add_argument('action', nargs='?', choices=['list', 'clear'], default='stats',
                        help='Action (default: show stats)')
    stats_p.add_argument('--limit', type=int, default=20, help='Number of jobs to list')

    # Cover
    cover_p = subparsers.add_parser('cover', help='Extract or inject cover art')
    cover_p.add_argument('action', choices=['extract', 'inject'])
    cover_p.add_argument('input', help='Audio file')
    cover_p.add_argument('--cover', help='Cover image (for inject)')
    cover_p.add_argument('--output', '-o', default='', help='Output path')

    # System
    subparsers.add_parser('system', help='Show system resource information')

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
    elif args.command == 'magic':
        magic_command(args)
    elif args.command == 'abogen':
        abogen_command(args)
    elif args.command == 'epub':
        epub_command(args)
    elif args.command == 'audio-glue':
        audio_glue_command(args)
    elif args.command == 'health':
        health_command(args)
    elif args.command == 'profile':
        profile_command(args)
    elif args.command == 'cache':
        cache_command(args)
    elif args.command == 'demux':
        demux_command(args)
    elif args.command == 'silence-chapter':
        silence_chapter_command(args)
    elif args.command == 'estimate':
        estimate_command(args)
    elif args.command == 'trim':
        trim_command(args)
    elif args.command == 'stats':
        stats_command(args)
    elif args.command == 'cover':
        cover_command(args)
    elif args.command == 'system':
        system_command(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
