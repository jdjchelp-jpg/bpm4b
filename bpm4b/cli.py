#!/usr/bin/env python3
"""
BPM4B CLI - Professional Multimedia Suite v9.0.0
"""

import sys
import argparse
import os
import json
import logging
from .app import app
from .core import convert_mp3_to_m4b, convert_m4b_to_mp3, parse_time_to_seconds

def web_command(args):
    """Start the web interface"""
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║              BPM4B Professional Suite v9.0.0                  ║
║                                                               ║
║  Web interface starting...                                    ║
║  URL: http://{args.host if args.host != '0.0.0.0' else 'localhost'}:{args.port}                    ║
║  AI Engine: Kokoro-82M Local                                  ║
╚═══════════════════════════════════════════════════════════════╝
    """)
    app.run(host=args.host, port=args.port, debug=args.debug)

def convert_command(args):
    """Unified conversion command"""
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
    """Generate audiobook from document"""
    try:
        from .document_parser import parse_document
        from .tts import generate_tts
    except ImportError:
        print("Error: Document parser or TTS engine dependencies (kokoro, mammoth, etc.) not found.")
        print("Install them with: pip install mammoth PyPDF2 ebooklib kokoro")
        sys.exit(1)

    if not os.path.exists(args.input):
        print(f"Error: Input file '{args.input}' not found", file=sys.stderr)
        sys.exit(1)
        
    print(f"[*] Extracting text from {args.input}...")
    doc = parse_document(args.input)
    
    work_wav = f"tmp_{os.getpid()}.wav"
    try:
        print(f"[*] Generating AI Speech ({args.voice})...")
        generate_tts(doc['text'], work_wav, voice=args.voice, speed=args.speed)
        
        print(f"[*] Finalizing M4B...")
        convert_mp3_to_m4b(work_wav, args.output)
        print(f"✓ Audiobook ready: {args.output}")
    finally:
        if os.path.exists(work_wav):
            os.remove(work_wav)

def main():
    parser = argparse.ArgumentParser(description="BPM4B - Professional Audio Suite")
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
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
