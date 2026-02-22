"""
Core functions shared between the main app and Vercel API.
"""

import os
import uuid
import subprocess
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def parse_time_to_seconds(time_input):
    """
    Parse time input to seconds.
    
    Supports:
    - Integer/float seconds (e.g., 390, 390.5)
    - MM:SS format (e.g., "6:30" -> 390)
    - MM:SS.sss format (e.g., "6:30.5" -> 390.5)
    
    Returns:
        float: Time in seconds
    
    Raises:
        ValueError: If the format is invalid
    """
    if isinstance(time_input, (int, float)):
        return float(time_input)
    
    if isinstance(time_input, str):
        # Check if it's a simple number string
        try:
            return float(time_input)
        except ValueError:
            pass
        
        # Try MM:SS or M:SS or MM:SS.sss format
        parts = time_input.strip().split(':')
        if len(parts) == 2:
            try:
                minutes = float(parts[0])
                seconds = float(parts[1])
                return minutes * 60 + seconds
            except ValueError:
                pass
    
    raise ValueError(f"Invalid time format: {time_input}. Use seconds (e.g., 390) or MM:SS (e.g., '6:30')")

def convert_mp3_to_m4b(mp3_path, output_path, chapters=None):
    """Convert MP3 to M4B with optional chapters using ffmpeg"""
    try:
        # Build ffmpeg command
        cmd = ['ffmpeg', '-i', mp3_path, '-c:a', 'aac', '-b:a', '64k']

        # Add chapter metadata if provided
        if chapters:
            # Create a chapter file for ffmpeg
            chapter_file = os.path.join(os.path.dirname(output_path), 'chapters.txt')
            with open(chapter_file, 'w') as f:
                f.write(';FFMETADATA1\n')
                for i, chapter in enumerate(chapters):
                    start_time = chapter['start_time']
                    end_time = chapter['end_time'] if i < len(chapters) - 1 else None

                    f.write(f'[CHAPTER]\n')
                    f.write(f'TIMEBASE=1/1000\n')
                    f.write(f'START={int(start_time * 1000)}\n')
                    if end_time:
                        f.write(f'END={int(end_time * 1000)}\n')
                    f.write(f'title={chapter["title"]}\n\n')

            cmd.extend(['-i', chapter_file, '-map_metadata', '1'])

        cmd.append(output_path)

        # Run ffmpeg
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise Exception(f"FFmpeg error: {result.stderr}")

        return True

    except Exception as e:
        logger.error(f"Error in convert_mp3_to_m4b: {e}")
        raise
