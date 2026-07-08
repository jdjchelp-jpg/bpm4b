"""
Metadata Module
Extract, apply, and look up metadata for M4B/M4A audiobook files.
Enhanced in v13 to integrate with cover_art and text_processor modules.
Ported from Node.js lib/server.js metadata endpoints.
"""

import os
import re
import json
import subprocess
import logging
import base64
import requests

from .cover_art import (
    extract_cover_art as _extract_cover_binary,
    inject_cover_art as _inject_cover_binary,
    extract_chapters_from_m4b,
    write_chapters_to_m4b,
    inherit_metadata_from_first_file,
)

logger = logging.getLogger(__name__)


def extract_metadata(file_path):
    """
    Extract metadata from an M4B/M4A file using ffprobe.
    Returns dict with title, author, genre, description, cover (base64).
    """
    cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json',
           '-show_format', '-show_streams', file_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise Exception(f"ffprobe error: {result.stderr}")

        data = json.loads(result.stdout)
        format_tags = data.get('format', {}).get('tags', {})
        streams = data.get('streams', [])

        metadata = {
            'title': format_tags.get('title', ''),
            'author': format_tags.get('artist', '') or format_tags.get('author', ''),
            'genre': format_tags.get('genre', ''),
            'description': format_tags.get('description', '') or format_tags.get('comment', ''),
            'album': format_tags.get('album', ''),
            'date': format_tags.get('date', ''),
            'track': format_tags.get('track', ''),
            'duration': data.get('format', {}).get('duration', '0'),
            'cover_base64': None,
        }

        # Extract cover art from streams
        for stream in streams:
            if stream.get('codec_type') == 'video' and stream.get('codec_name') in ('mjpeg', 'png'):
                # Use ffmpeg to extract cover to a temp file
                cover_path = file_path + '.cover.jpg'
                try:
                    extract_cmd = ['ffmpeg', '-y', '-i', file_path,
                                   '-map', f'0:{stream["index"]}',
                                   '-c:v', 'copy', cover_path]
                    subprocess.run(extract_cmd, capture_output=True, text=True, timeout=30)
                    if os.path.exists(cover_path) and os.path.getsize(cover_path) > 0:
                        with open(cover_path, 'rb') as f:
                            img_data = f.read()
                            metadata['cover_base64'] = base64.b64encode(img_data).decode('utf-8')
                except Exception as e:
                    logger.warning(f"Could not extract cover: {e}")
                finally:
                    try:
                        os.remove(cover_path)
                    except OSError:
                        pass
                break

        return metadata

    except Exception as e:
        logger.error(f"Metadata extraction error: {e}")
        raise


def apply_metadata(file_path, output_path, metadata, cover_base64=None):
    """
    Apply metadata and optional cover art to an M4B/M4A file.
    Uses ffmpeg to remux with new metadata.
    """
    tags = {
        'title': metadata.get('title', ''),
        'artist': metadata.get('author', '') or metadata.get('artist', ''),
        'genre': metadata.get('genre', ''),
        'description': metadata.get('description', '') or metadata.get('comment', ''),
        'album': metadata.get('album', '') or metadata.get('title', ''),
        'date': metadata.get('date', ''),
        'track': str(metadata.get('track', '')),
    }

    cmd = ['ffmpeg', '-y', '-i', file_path]

    # Add cover art if provided
    tmp_cover = None
    if cover_base64:
        tmp_cover = file_path + '.tmp_cover.jpg'
        try:
            img_data = base64.b64decode(cover_base64)
            with open(tmp_cover, 'wb') as f:
                f.write(img_data)
            cmd.extend(['-i', tmp_cover, '-map', '0', '-map', '1',
                        '-c:v', 'mjpeg', '-disposition:v:1', 'attached_pic'])
        except Exception as e:
            logger.warning(f"Cover image error: {e}")
            tmp_cover = None

    # Set metadata
    for key, value in tags.items():
        if value:
            cmd.extend(['-metadata', f'{key}={value}'])

    cmd.extend(['-c:a', 'copy', '-movflags', '+faststart'])
    cmd.append(output_path)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise Exception(f"Metadata apply error: {result.stderr}")
        return True
    finally:
        if tmp_cover and os.path.exists(tmp_cover):
            try:
                os.remove(tmp_cover)
            except OSError:
                pass


def lookup_open_library(title='', author=''):
    """
    Lookup book metadata from Open Library API.
    Returns list of matching works with metadata.
    """
    query_parts = []
    if title:
        query_parts.append(f'title:{title}')
    if author:
        query_parts.append(f'author:{author}')

    if not query_parts:
        return []

    query = ' '.join(query_parts)
    url = 'https://openlibrary.org/search.json'
    params = {'q': query, 'limit': 10}

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for doc in data.get('docs', []):
            results.append({
                'title': doc.get('title', ''),
                'author': ', '.join(doc.get('author_name', [])),
                'first_publish_year': doc.get('first_publish_year'),
                'publisher': ', '.join(doc.get('publisher', [])[:3]),
                'isbn': doc.get('isbn', [''])[0] if doc.get('isbn') else '',
                'cover_url': f"https://covers.openlibrary.org/b/id/{doc.get('cover_i', '')}-L.jpg" if doc.get('cover_i') else None,
                'description': doc.get('first_sentence', [''])[0] if doc.get('first_sentence') else '',
            })

        return results

    except requests.RequestException as e:
        logger.error(f"Open Library lookup failed: {e}")
        return []


def fetch_cover_from_open_library(cover_url):
    """Fetch cover art from Open Library and return as base64."""
    if not cover_url:
        return None
    try:
        resp = requests.get(cover_url, timeout=15)
        if resp.status_code == 200:
            return base64.b64encode(resp.content).decode('utf-8')
    except Exception as e:
        logger.warning(f"Cover fetch failed: {e}")
    return None
