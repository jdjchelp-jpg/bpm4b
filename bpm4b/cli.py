#!/usr/bin/env python3
"""
Command-line interface for BPM4B (MP3 to M4B Converter).

Usage:
    bpm4b web [options]    Start the web interface
    bpm4b convert [args]   Convert MP3 to M4B from command line
    bpm4b --help           Show help
"""

import sys
import argparse
import os
from .app import app
from .core import convert_mp3_to_m4b, parse_time_to_seconds

def web_command(args):
    """Start the web interface"""
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║              MP3 to M4B Converter v{__import__('bpm4b').__version__}                      ║
║                                                               ║
║  Web interface starting...                                    ║
║  URL: http://{args.host if args.host != '0.0.0.0' else 'localhost'}:{args.port}                    ║
║  Debug mode: {'ON' if args.debug else 'OFF'}                                   ║
╚═══════════════════════════════════════════════════════════════╝
    """)
    
    try:
        app.run(host=args.host, port=args.port, debug=args.debug)
    except KeyboardInterrupt:
        print("\n\nServer stopped. Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"Error starting server: {e}", file=sys.stderr)
        sys.exit(1)

def convert_command(args):
    """Convert MP3 to M4B from command line"""
    import subprocess
    
    if not os.path.exists(args.input):
        print(f"Error: Input file '{args.input}' not found", file=sys.stderr)
        sys.exit(1)
    
    # Ensure output directory exists
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    # Check FFmpeg
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: FFmpeg is not installed or not in PATH", file=sys.stderr)
        print("Install FFmpeg: https://ffmpeg.org/download.html", file=sys.stderr)
        sys.exit(1)
    
    print(f"Converting: {args.input} -> {args.output}")
    
    try:
        convert_mp3_to_m4b(args.input, args.output, args.chapters)
        print(f"✓ Conversion complete: {args.output}")
    except Exception as e:
        print(f"Error during conversion: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    """Main entry point for the CLI command"""
    parser = argparse.ArgumentParser(
        description="MP3 to M4B Audiobook Converter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start web interface
  bpm4b web
  bpm4b web --port 8080
  bpm4b web --host 127.0.0.1 --debug

  # Convert MP3 to M4B
  bpm4b convert input.mp3 output.m4b
  bpm4b convert input.mp3 output.m4b --chapter "Chapter 1" 0
  bpm4b convert input.mp3 output.m4b --chapter "Intro" 0 --chapter "Chapter 1" 3600
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Web command
    web_parser = subparsers.add_parser('web', help='Start the web interface')
    web_parser.add_argument('--host', default='0.0.0.0',
                           help='Host to bind to (default: 0.0.0.0)')
    web_parser.add_argument('--port', type=int, default=5000,
                           help='Port to bind to (default: 5000)')
    web_parser.add_argument('--debug', action='store_true',
                           help='Enable debug mode')
    
    # Convert command
    convert_parser = subparsers.add_parser('convert', help='Convert MP3 to M4B')
    convert_parser.add_argument('input', help='Input MP3 file path')
    convert_parser.add_argument('output', help='Output M4B file path')
    convert_parser.add_argument('--chapter', nargs=2, metavar=('TITLE', 'START_TIME'),
                               action='append',
                               help='Add chapter marker (title and start time in seconds or MM:SS format, e.g., 390 or "6:30")')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    if args.command == 'web':
        web_command(args)
    elif args.command == 'convert':
        # Convert chapter arguments to proper format
        if args.chapter:
            chapters = []
            for title, start_time in args.chapter:
                try:
                    parsed_time = parse_time_to_seconds(start_time)
                except ValueError as e:
                    print(f"Error: Invalid time format for chapter '{title}': {e}", file=sys.stderr)
                    sys.exit(1)
                chapters.append({
                    'title': title,
                    'start_time': parsed_time
                })
            args.chapters = chapters
        else:
            args.chapters = None
        convert_command(args)

if __name__ == '__main__':
    main()
