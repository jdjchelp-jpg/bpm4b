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

def convert_mp3_to_m4b(mp3_path, output_path, chapters=None, quality='64k'):
    """Convert MP3 to M4B with optional chapters using ffmpeg"""
    try:
        # Build ffmpeg command
        # -y to overwrite output
        cmd = ['ffmpeg', '-y', '-i', mp3_path]

        # Add chapter metadata if provided
        chapter_file = None
        if chapters:
            # Create a chapter file for ffmpeg
            chapter_file = os.path.join(os.path.dirname(output_path), f'chapters_{uuid.uuid4().hex[:8]}.txt')
            with open(chapter_file, 'w', encoding='utf-8') as f:
                f.write(';FFMETADATA1\n')
                for i, chapter in enumerate(chapters):
                    start_time = parse_time_to_seconds(chapter['start_time'])
                    # If end_time not provided, estimate it or use next chapter start
                    if 'end_time' in chapter and chapter['end_time']:
                        end_time = parse_time_to_seconds(chapter['end_time'])
                    elif i < len(chapters) - 1:
                        end_time = parse_time_to_seconds(chapters[i+1]['start_time'])
                    else:
                        # For last chapter, we'd ideally need the duration, 
                        # but FFmpeg handles open-ended chapters or we can just use a large number if needed
                        # However, it's better to leave it out or estimate.
                        end_time = start_time + 0.001 

                    f.write(f'[CHAPTER]\n')
                    f.write(f'TIMEBASE=1/1000\n')
                    f.write(f'START={int(start_time * 1000)}\n')
                    f.write(f'END={int(end_time * 1000)}\n')
                    f.write(f'title={chapter["title"]}\n\n')

            cmd.extend(['-i', chapter_file, '-map_metadata', '1'])

        # Audio settings
        cmd.extend(['-c:a', 'aac', '-b:a', quality])
        cmd.append(output_path)

        # Run ffmpeg
        logger.info(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Cleanup chapter file
        if chapter_file and os.path.exists(chapter_file):
            try:
                os.remove(chapter_file)
            except:
                pass

        if result.returncode != 0:
            raise Exception(f"FFmpeg error: {result.stderr}")

        return True

    except Exception as e:
        logger.error(f"Error in convert_mp3_to_m4b: {e}")
        raise

def convert_m4b_to_mp3(m4b_path, output_path, quality='128k'):
    """Convert M4B/M4A to MP3 using ffmpeg"""
    try:
        cmd = ['ffmpeg', '-y', '-i', m4b_path, '-c:a', 'libmp3lame', '-b:a', quality, output_path]
        logger.info(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise Exception(f"FFmpeg error: {result.stderr}")

        return True
    except Exception as e:
        logger.error(f"Error in convert_m4b_to_mp3: {e}")
        raise
