"""
Unit tests for BPM4B v12 features.
Tests for: convert_audio_format, audio_glue, metadata extract/apply/lookup,
document_to_epub, and core utility functions.

Run with: python -m pytest test_v12_features.py -v
       or: python test_v12_features.py
"""

import os
import sys
import json
import tempfile
import unittest
from unittest import mock
from xml.etree import ElementTree as ET
import zipfile
import requests

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════

def _fake_subprocess_run_success(*args, **kwargs):
    """Return a fake subprocess.CompletedProcess mimicking success."""
    class FakeResult:
        returncode = 0
        stdout = ''
        stderr = ''
    return FakeResult()


def _fake_subprocess_run_ffmpeg_version(*args, **kwargs):
    """Return fake ffmpeg -version output."""
    class FakeResult:
        returncode = 0
        stdout = 'ffmpeg version 7.0.1 Copyright (c) 2000-2024 the FFmpeg developers\n...'
        stderr = ''
    return FakeResult()


# ═══════════════════════════════════════════════════════════
# 1. Utility Functions (parse_time_to_seconds, check_ffmpeg)
# ═══════════════════════════════════════════════════════════

class TestParseTimeToSeconds(unittest.TestCase):
    """Test the time parsing utility."""

    def setUp(self):
        from bpm4b.core import parse_time_to_seconds
        self.parse = parse_time_to_seconds

    def test_seconds_int(self):
        self.assertEqual(self.parse(390), 390.0)

    def test_seconds_float(self):
        self.assertEqual(self.parse(390.5), 390.5)

    def test_mm_ss_string(self):
        self.assertEqual(self.parse('6:30'), 390.0)

    def test_mm_ss_leading_zero(self):
        self.assertEqual(self.parse('0:45'), 45.0)
        self.assertEqual(self.parse('00:45'), 45.0)

    def test_hh_mm_ss(self):
        self.assertEqual(self.parse('1:00:00'), 3600.0)
        self.assertEqual(self.parse('1:30:15'), 5415.0)

    def test_seconds_string(self):
        self.assertEqual(self.parse('390'), 390.0)
        self.assertEqual(self.parse('390.5'), 390.5)

    def test_mm_ss_fractional(self):
        self.assertEqual(self.parse('6:30.5'), 390.5)

    def test_invalid_format(self):
        with self.assertRaises(ValueError):
            self.parse('not-a-time')

    def test_invalid_format_empty(self):
        with self.assertRaises(ValueError):
            self.parse('')

    def test_invalid_format_letters(self):
        with self.assertRaises(ValueError):
            self.parse('abc:def')


class TestCheckFFmpeg(unittest.TestCase):
    """Test the ffmpeg availability check."""

    @mock.patch('bpm4b.core.subprocess.run')
    def test_ffmpeg_available(self, mock_run):
        from bpm4b.core import check_ffmpeg
        mock_run.return_value = _fake_subprocess_run_ffmpeg_version()
        result = check_ffmpeg()
        self.assertTrue(result['available'])
        self.assertIn('ffmpeg version', result['version'])

    @mock.patch('bpm4b.core.subprocess.run', side_effect=FileNotFoundError)
    def test_ffmpeg_not_found(self, mock_run):
        from bpm4b.core import check_ffmpeg
        result = check_ffmpeg()
        self.assertFalse(result['available'])
        self.assertIn('not found', result['error'])

    @mock.patch('bpm4b.core.subprocess.run', side_effect=Exception('Something broke'))
    def test_ffmpeg_unexpected_error(self, mock_run):
        from bpm4b.core import check_ffmpeg
        result = check_ffmpeg()
        self.assertFalse(result['available'])
        self.assertIn('Something broke', result['error'])


class TestGetAudioDuration(unittest.TestCase):
    """Test audio duration extraction."""

    @mock.patch('bpm4b.core.subprocess.run')
    def test_ffprobe_duration(self, mock_run):
        from bpm4b.core import get_audio_duration
        mock_result = mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({'format': {'duration': '123.456'}})
        mock_run.return_value = mock_result

        duration = get_audio_duration('/fake/file.mp3')
        self.assertAlmostEqual(duration, 123.456)

    @mock.patch('bpm4b.core.subprocess.run')
    def test_ffmpeg_fallback_duration(self, mock_run):
        from bpm4b.core import get_audio_duration
        second_result = mock.MagicMock()
        second_result.returncode = 0
        second_result.stdout = ''
        second_result.stderr = 'Duration: 00:05:30.50, start: ...'
        mock_run.side_effect = [Exception('ffprobe not found'), second_result]

        duration = get_audio_duration('/fake/file.mp3')
        self.assertAlmostEqual(duration, 330.5, places=1)

    def test_wav_header_duration(self):
        """Test duration estimation from a real WAV header file."""
        from bpm4b.core import get_audio_duration
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            fpath = f.name
            # Write a minimal valid WAV header + 1 second of silence
            import struct
            sample_rate = 24000
            num_samples = sample_rate  # 1 second
            data_size = num_samples * 2  # 16-bit mono
            header = struct.pack(
                '<4sI4s4sIHHIIHH4sI',
                b'RIFF', 36 + data_size, b'WAVE',
                b'fmt ', 16, 1, 1, sample_rate, sample_rate * 2, 2, 16,
                b'data', data_size
            )
            f.write(header)
            f.write(b'\x00\x00' * num_samples)  # silent PCM data

        duration = get_audio_duration(fpath)
        os.unlink(fpath)
        self.assertAlmostEqual(duration, 1.0, places=1)


# ═══════════════════════════════════════════════════════════
# 2. Audio Format Converter
# ═══════════════════════════════════════════════════════════

class TestConvertAudioFormat(unittest.TestCase):
    """Test the audio format converter function."""

    def setUp(self):
        from bpm4b.core import convert_audio_format
        self.convert = convert_audio_format

    def test_unsupported_format_raises(self):
        """Unsupported target format should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            self.convert('/in.mp3', '/out.xyz', target_format='xyz')
        self.assertIn('Unsupported', str(ctx.exception))
        self.assertIn('xyz', str(ctx.exception))

    @mock.patch('bpm4b.core.subprocess.run')
    def test_mp3_conversion(self, mock_run):
        """MP3 conversion should use libmp3lame codec."""
        mock_run.return_value = _fake_subprocess_run_success()
        result = self.convert('/in.wav', '/out.mp3', target_format='mp3', quality='192k')
        self.assertEqual(result, '/out.mp3')
        cmd = mock_run.call_args[0][0]
        self.assertIn('libmp3lame', cmd)
        self.assertIn('192k', cmd)

    @mock.patch('bpm4b.core.subprocess.run')
    def test_wav_conversion(self, mock_run):
        """WAV conversion should use pcm_s16le, no bitrate."""
        mock_run.return_value = _fake_subprocess_run_success()
        result = self.convert('/in.mp3', '/out.wav', target_format='wav')
        self.assertEqual(result, '/out.wav')
        cmd = mock_run.call_args[0][0]
        self.assertIn('pcm_s16le', cmd)
        # WAV should not have bitrate
        bitrate_args = [a for a in cmd if a in ('-b:a', '192k', '128k')]
        self.assertEqual(len(bitrate_args), 0)

    @mock.patch('bpm4b.core.subprocess.run')
    def test_flac_conversion(self, mock_run):
        """FLAC conversion should use flac codec, no bitrate."""
        mock_run.return_value = _fake_subprocess_run_success()
        result = self.convert('/in.mp3', '/out.flac', target_format='flac')
        self.assertEqual(result, '/out.flac')
        cmd = mock_run.call_args[0][0]
        self.assertIn('flac', cmd)
        bitrate_args = [a for a in cmd if a in ('-b:a',)]
        self.assertEqual(len(bitrate_args), 0)

    @mock.patch('bpm4b.core.subprocess.run')
    def test_aac_conversion(self, mock_run):
        """AAC conversion should use aac codec with bitrate."""
        mock_run.return_value = _fake_subprocess_run_success()
        result = self.convert('/in.mp3', '/out.aac', target_format='aac', quality='256k')
        self.assertEqual(result, '/out.aac')
        cmd = mock_run.call_args[0][0]
        self.assertIn('aac', cmd)
        self.assertIn('256k', cmd)

    @mock.patch('bpm4b.core.subprocess.run')
    def test_ogg_conversion(self, mock_run):
        """OGG conversion should use libvorbis codec."""
        mock_run.return_value = _fake_subprocess_run_success()
        result = self.convert('/in.mp3', '/out.ogg', target_format='ogg')
        self.assertEqual(result, '/out.ogg')
        cmd = mock_run.call_args[0][0]
        self.assertIn('libvorbis', cmd)

    @mock.patch('bpm4b.core.subprocess.run')
    def test_alac_conversion_adds_faststart(self, mock_run):
        """ALAC conversion should add movflags for faststart."""
        mock_run.return_value = _fake_subprocess_run_success()
        result = self.convert('/in.mp3', '/out.m4a', target_format='alac')
        self.assertEqual(result, '/out.m4a')
        cmd = mock_run.call_args[0][0]
        self.assertIn('alac', cmd)
        self.assertIn('+faststart', ''.join(cmd))

    @mock.patch('bpm4b.core.subprocess.run')
    def test_extension_fix(self, mock_run):
        """If output path has wrong extension, should fix it."""
        mock_run.return_value = _fake_subprocess_run_success()
        result = self.convert('/in.wav', '/out.wrong', target_format='mp3')
        self.assertTrue(result.endswith('.mp3'))
        self.assertIn('libmp3lame', mock_run.call_args[0][0])

    @mock.patch('bpm4b.core.subprocess.run')
    def test_ffmpeg_failure_propagates(self, mock_run):
        """FFmpeg error should be raised as Exception."""
        bad_result = mock.MagicMock()
        bad_result.returncode = 1
        bad_result.stderr = 'ffmpeg error: invalid data found'
        mock_run.return_value = bad_result
        with self.assertRaises(Exception) as ctx:
            self.convert('/in.mp3', '/out.mp3', target_format='mp3')
        self.assertIn('ffmpeg', str(ctx.exception).lower())


# ═══════════════════════════════════════════════════════════
# 3. Audio Glue (Batch Merge)
# ═══════════════════════════════════════════════════════════

class TestAudioGlue(unittest.TestCase):
    """Test the audio merge function."""

    def setUp(self):
        from bpm4b.core import audio_glue
        self.glue = audio_glue

    def test_empty_input_raises(self):
        """Empty input should raise ValueError."""
        with self.assertRaises(ValueError):
            self.glue([], '/out.m4b')

    @mock.patch('bpm4b.core.subprocess.run')
    def test_single_input_accepted(self, mock_run):
        """Single input should be accepted and processed."""
        mock_run.return_value = _fake_subprocess_run_success()
        result = self.glue(['/single.mp3'], '/out.m4b')
        self.assertEqual(result, '/out.m4b')

    @mock.patch('bpm4b.core.subprocess.run')
    def test_basic_merge(self, mock_run):
        """Basic merge without normalization should concat files."""
        mock_run.return_value = _fake_subprocess_run_success()
        result = self.glue(['/a.mp3', '/b.mp3'], '/out.m4b', normalize=False)
        self.assertEqual(result, '/out.m4b')
        # Should call ffmpeg to concat
        cmd = mock_run.call_args[0][0]
        self.assertIn('concat', cmd)
        self.assertIn('aac', cmd)

    @mock.patch('bpm4b.core.subprocess.run')
    def test_merge_with_normalize(self, mock_run):
        """Normalize should add loudnorm filter."""
        mock_run.return_value = _fake_subprocess_run_success()
        self.glue(['/a.mp3', '/b.mp3'], '/out.m4b', normalize=True)
        # First call is normalization
        first_cmd = mock_run.call_args_list[0][0][0]
        self.assertIn('loudnorm', ''.join(first_cmd))

    @mock.patch('bpm4b.core.subprocess.run')
    def test_merge_with_volume(self, mock_run):
        """Volume adjustment should add volume filter."""
        mock_run.return_value = _fake_subprocess_run_success()
        self.glue(['/a.mp3', '/b.mp3'], '/out.m4b', volume=1.5)
        cmd = mock_run.call_args[0][0]
        self.assertIn('volume=1.5', ''.join(cmd))

    @mock.patch('bpm4b.core.tempfile.mkdtemp')
    @mock.patch('bpm4b.core.subprocess.run')
    def test_merge_cleanup_temp_files(self, mock_run, mock_mkdtemp):
        """Temp concat list file should be cleaned up after merge."""
        mock_run.return_value = _fake_subprocess_run_success()
        with tempfile.TemporaryDirectory() as tmpdir:
            # Force work_dir inside our controlled tmpdir for inspection
            mock_mkdtemp.return_value = os.path.join(tmpdir, 'work')
            os.makedirs(os.path.join(tmpdir, 'work'))

            a = os.path.join(tmpdir, 'a.mp3')
            b = os.path.join(tmpdir, 'b.mp3')
            with open(a, 'w') as f: f.write('')
            with open(b, 'w') as f: f.write('')
            out = os.path.join(tmpdir, 'out.m4b')
            self.glue([a, b], out)

            # work_dir may be removed by rmdir (clean) or still exist but empty
            work_path = os.path.join(tmpdir, 'work')
            if os.path.exists(work_path):
                remaining = os.listdir(work_path)
                self.assertEqual(len(remaining), 0,
                                 f"Expected empty work_dir, got: {remaining}")
            # else: directory was cleaned up entirely — also success

    @mock.patch('bpm4b.core.subprocess.run')
    def test_ffmpeg_error_propagates(self, mock_run):
        """FFmpeg failure should raise Exception."""
        bad_result = mock.MagicMock()
        bad_result.returncode = 1
        bad_result.stderr = 'concat error'
        mock_run.return_value = bad_result
        with self.assertRaises(Exception) as ctx:
            self.glue(['/a.mp3', '/b.mp3'], '/out.m4b')
        self.assertIn('merge', str(ctx.exception).lower())


# ═══════════════════════════════════════════════════════════
# 4. Metadata Module
# ═══════════════════════════════════════════════════════════

class TestExtractMetadata(unittest.TestCase):
    """Test metadata extraction from M4B files."""

    def setUp(self):
        from bpm4b.metadata import extract_metadata
        self.extract = extract_metadata

    @mock.patch('bpm4b.metadata.subprocess.run')
    def test_extract_basic_metadata(self, mock_run):
        """Should extract standard metadata fields from ffprobe JSON."""
        ffprobe_output = {
            'format': {
                'tags': {
                    'title': 'My Audiobook',
                    'artist': 'John Doe',
                    'genre': 'Fiction',
                    'description': 'A great story',
                    'album': 'My Audiobook',
                    'date': '2024',
                    'track': '1',
                },
                'duration': '3600.0',
            },
            'streams': [],
        }
        mock_result = mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(ffprobe_output)
        mock_run.return_value = mock_result

        meta = self.extract('/fake/file.m4b')
        self.assertEqual(meta['title'], 'My Audiobook')
        self.assertEqual(meta['author'], 'John Doe')
        self.assertEqual(meta['genre'], 'Fiction')
        self.assertEqual(meta['description'], 'A great story')
        self.assertEqual(meta['duration'], '3600.0')

    @mock.patch('bpm4b.metadata.subprocess.run')
    def test_extract_empty_metadata(self, mock_run):
        """Should handle files with no metadata tags."""
        ffprobe_output = {
            'format': {'tags': {}, 'duration': '0'},
            'streams': [],
        }
        mock_result = mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(ffprobe_output)
        mock_run.return_value = mock_result

        meta = self.extract('/fake/file.m4b')
        self.assertEqual(meta['title'], '')
        self.assertEqual(meta['author'], '')
        self.assertEqual(meta['genre'], '')
        self.assertEqual(meta['cover_base64'], None)

    @mock.patch('bpm4b.metadata.subprocess.run')
    def test_extract_ffprobe_error(self, mock_run):
        """FFprobe failure should raise an exception."""
        bad_result = mock.MagicMock()
        bad_result.returncode = 1
        bad_result.stderr = 'ffprobe error'
        mock_run.return_value = bad_result
        with self.assertRaises(Exception):
            self.extract('/fake/file.m4b')

    @mock.patch('bpm4b.metadata.subprocess.run')
    def test_extract_author_fallback(self, mock_run):
        """If 'artist' is missing, should fall back to 'author' tag."""
        ffprobe_output = {
            'format': {
                'tags': {'author': 'Jane Smith'},
                'duration': '100',
            },
            'streams': [],
        }
        mock_result = mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(ffprobe_output)
        mock_run.return_value = mock_result

        meta = self.extract('/fake/file.m4b')
        self.assertEqual(meta['author'], 'Jane Smith')


class TestApplyMetadata(unittest.TestCase):
    """Test applying metadata to M4B files."""

    def setUp(self):
        from bpm4b.metadata import apply_metadata
        self.apply = apply_metadata

    @mock.patch('bpm4b.metadata.subprocess.run')
    def test_apply_basic_metadata(self, mock_run):
        """Should construct correct ffmpeg command with metadata."""
        mock_run.return_value = _fake_subprocess_run_success()
        metadata = {
            'title': 'Test Book',
            'author': 'Test Author',
            'genre': 'Non-Fiction',
            'description': 'A test',
        }
        result = self.apply('/in.m4b', '/out.m4b', metadata)
        self.assertTrue(result)
        cmd = mock_run.call_args[0][0]
        # Should have metadata flags
        self.assertIn('-metadata', cmd)
        self.assertIn('title=Test Book', ''.join(cmd))
        self.assertIn('artist=Test Author', ''.join(cmd))
        self.assertIn('genre=Non-Fiction', ''.join(cmd))

    @mock.patch('bpm4b.metadata.subprocess.run')
    def test_apply_with_cover(self, mock_run):
        """Should include cover art in ffmpeg command."""
        mock_run.return_value = _fake_subprocess_run_success()
        metadata = {'title': 'Book'}
        cover_b64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='

        result = self.apply('/in.m4b', '/out.m4b', metadata, cover_base64=cover_b64)
        self.assertTrue(result)

    @mock.patch('bpm4b.metadata.subprocess.run')
    def test_apply_empty_metadata(self, mock_run):
        """Empty metadata should not add -metadata flags."""
        mock_run.return_value = _fake_subprocess_run_success()
        result = self.apply('/in.m4b', '/out.m4b', {})
        self.assertTrue(result)
        cmd = mock_run.call_args[0][0]
        metadata_flags = [i for i, x in enumerate(cmd) if x == '-metadata']
        # Should have our default album tag and date/track if present
        # Actually with empty metadata, album defaults to title (which is empty)
        # and date/track are also empty, so no metadata flags expected
        # But there's always album = metadata.get('album', '') or metadata.get('title', '')
        # which is '' - no metadata flags then
        self.assertEqual(len(metadata_flags), 0)

    @mock.patch('bpm4b.metadata.subprocess.run')
    def test_apply_ffmpeg_error(self, mock_run):
        """FFmpeg failure should raise Exception."""
        bad_result = mock.MagicMock()
        bad_result.returncode = 1
        bad_result.stderr = 'metadata apply failed'
        mock_run.return_value = bad_result

        with self.assertRaises(Exception) as ctx:
            self.apply('/in.m4b', '/out.m4b', {'title': 'Book'})
        self.assertIn('metadata', str(ctx.exception).lower())


class TestLookupOpenLibrary(unittest.TestCase):
    """Test Open Library metadata lookup."""

    def setUp(self):
        from bpm4b.metadata import lookup_open_library
        self.lookup = lookup_open_library

    @mock.patch('bpm4b.metadata.requests.get')
    def test_lookup_by_title(self, mock_get):
        """Should return results when searching by title."""
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'docs': [
                {
                    'title': 'The Great Gatsby',
                    'author_name': ['F. Scott Fitzgerald'],
                    'first_publish_year': 1925,
                    'publisher': ['Charles Scribner\'s Sons'],
                    'isbn': ['9780743273565'],
                    'cover_i': 12345,
                }
            ]
        }
        mock_get.return_value = mock_response

        results = self.lookup(title='Great Gatsby')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], 'The Great Gatsby')
        self.assertEqual(results[0]['author'], 'F. Scott Fitzgerald')
        self.assertEqual(results[0]['first_publish_year'], 1925)
        self.assertIsNotNone(results[0]['cover_url'])

    @mock.patch('bpm4b.metadata.requests.get')
    def test_lookup_empty(self, mock_get):
        """Empty query should return empty list."""
        results = self.lookup()
        self.assertEqual(results, [])
        mock_get.assert_not_called()

    @mock.patch('bpm4b.metadata.requests.get')
    def test_lookup_no_results(self, mock_get):
        """No results should return empty list."""
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'docs': []}
        mock_get.return_value = mock_response

        results = self.lookup(title='xyzzy_nonexistent')
        self.assertEqual(results, [])

    @mock.patch('bpm4b.metadata.requests.get', side_effect=requests.exceptions.ConnectionError('Network error'))
    def test_lookup_network_error(self, mock_get):
        """Network error should return empty list gracefully."""
        results = self.lookup(title='Test')
        self.assertEqual(results, [])


# ═══════════════════════════════════════════════════════════
# 5. Document to EPUB
# ═══════════════════════════════════════════════════════════

class TestConvertToEpub(unittest.TestCase):
    """Test document to EPUB conversion."""

    def _verify_epub_structure(self, epub_path):
        """Verify an EPUB file has valid structure."""
        self.assertTrue(os.path.exists(epub_path))
        self.assertTrue(os.path.getsize(epub_path) > 100)

        with zipfile.ZipFile(epub_path, 'r') as z:
            names = z.namelist()
            # Must have mimetype first (uncompressed)
            self.assertIn('mimetype', names)
            # Must have META-INF/container.xml
            self.assertIn('META-INF/container.xml', names)
            # Must have OEBPS/ directory
            oebps_files = [n for n in names if n.startswith('OEBPS/')]
            self.assertGreater(len(oebps_files), 0)
            # Should have content.opf
            self.assertIn('OEBPS/content.opf', names)
            # Should have at least one chapter
            chapter_files = [n for n in names if n.startswith('OEBPS/chapter_')]
            self.assertGreater(len(chapter_files), 0)

    def test_txt_to_epub(self):
        """Convert a plain text file to EPUB."""
        from bpm4b.document_to_epub import convert_to_epub

        with tempfile.TemporaryDirectory() as tmpdir:
            txt_path = os.path.join(tmpdir, 'test_book.txt')
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write("""This is a test paragraph for the audiobook converter.

Chapter 1
This is the first chapter content. It has multiple sentences.
Here is more text in chapter one.

Chapter 2
This is the second chapter with different content.
More text here for chapter two.
""")

            epub_path = os.path.join(tmpdir, 'output.epub')
            result = convert_to_epub(txt_path, epub_path, {
                'title': 'Test Book',
                'author': 'Test Author',
            })

            self.assertEqual(result['title'], 'Test Book')
            self.assertEqual(result['author'], 'Test Author')
            self._verify_epub_structure(epub_path)

    def test_txt_to_epub_no_headings(self):
        """Text without chapter headings should still produce valid EPUB."""
        from bpm4b.document_to_epub import convert_to_epub

        with tempfile.TemporaryDirectory() as tmpdir:
            txt_path = os.path.join(tmpdir, 'plain.txt')
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write("This is a plain text document without any chapter headings. " * 20)

            epub_path = os.path.join(tmpdir, 'plain.epub')
            result = convert_to_epub(txt_path, epub_path)
            self._verify_epub_structure(epub_path)
            # Title should default to filename
            self.assertEqual(result['title'], 'plain')
            self.assertEqual(result['author'], 'Unknown')

    def test_epub_metadata_embedded(self):
        """Verify metadata is properly embedded in the EPUB OPF file."""
        from bpm4b.document_to_epub import convert_to_epub

        with tempfile.TemporaryDirectory() as tmpdir:
            txt_path = os.path.join(tmpdir, 'meta_test.txt')
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write("Some simple text content for metadata verification.\n" * 5)

            epub_path = os.path.join(tmpdir, 'meta_test.epub')
            convert_to_epub(txt_path, epub_path, {
                'title': 'Metadata Title',
                'author': 'Metadata Author',
                'language': 'fr',
            })

            # Extract and verify OPF
            with zipfile.ZipFile(epub_path, 'r') as z:
                opf_content = z.read('OEBPS/content.opf').decode('utf-8')
            self.assertIn('Metadata Title', opf_content)
            self.assertIn('Metadata Author', opf_content)
            self.assertIn('fr', opf_content)

    def test_split_into_chapters_with_headings(self):
        """Test chapter splitting using detected headings."""
        from bpm4b.document_to_epub import _split_into_chapters

        text = """Introduction text here.

Chapter 1: The Beginning
Some content for chapter one.
More text.

Chapter 2: The Middle
Content for the second chapter.
"""

        headings = [
            {'text': 'Chapter 1: The Beginning', 'level': 2, 'position': 27},
            {'text': 'Chapter 2: The Middle', 'level': 2, 'position': 78},
        ]

        chapters = _split_into_chapters(text, headings)
        self.assertGreaterEqual(len(chapters), 2)

    def test_escape_xml(self):
        """Test XML escaping for EPUB content."""
        from bpm4b.document_to_epub import _escape_xml
        self.assertEqual(_escape_xml('AT&T'), 'AT&amp;T')
        self.assertEqual(_escape_xml('<hello>'), '&lt;hello&gt;')
        self.assertEqual(_escape_xml('"quoted"'), '&quot;quoted&quot;')
        self.assertEqual(_escape_xml("it's"), 'it&apos;s')
        self.assertEqual(_escape_xml('normal text'), 'normal text')

    def test_conversion_requires_text(self):
        """Empty document should raise ValueError."""
        from bpm4b.document_to_epub import convert_to_epub
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_path = os.path.join(tmpdir, 'empty.txt')
            with open(empty_path, 'w', encoding='utf-8') as f:
                f.write('   \n\n  ')
            epub_path = os.path.join(tmpdir, 'empty.epub')
            with self.assertRaises(ValueError):
                convert_to_epub(empty_path, epub_path)


# ═══════════════════════════════════════════════════════════
# 6. End-to-End: Flask API Validation
# ═══════════════════════════════════════════════════════════

class TestAppHealth(unittest.TestCase):
    """Test the Flask app health endpoint."""

    def setUp(self):
        from bpm4b.app import app
        self.app = app.test_client()

    @mock.patch('bpm4b.app.check_ffmpeg')
    def test_health_endpoint(self, mock_ffmpeg):
        """Health endpoint should return version and ffmpeg status."""
        mock_ffmpeg.return_value = {'available': True, 'version': 'ffmpeg 7.0'}
        resp = self.app.get('/api/health')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['version'], '12.0.0')
        self.assertTrue(data['ffmpeg']['available'])


class TestFlaskEndpoints(unittest.TestCase):
    """Test Flask API endpoint validation (no audio files)."""

    def setUp(self):
        from bpm4b.app import app
        self.app = app.test_client()

    def test_convert_no_file(self):
        """Convert endpoint should return 400 when no file provided."""
        resp = self.app.post('/api/convert')
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn('error', data)

    def test_mp3_to_m4b_no_file(self):
        """MP3 to M4B endpoint should return 400 when no file provided."""
        resp = self.app.post('/api/mp3-to-m4b')
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn('error', data)

    def test_convert_audio_no_file(self):
        """Audio format converter should return 400 when no file provided."""
        resp = self.app.post('/api/convert-audio')
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn('error', data)

    def test_audio_glue_no_file(self):
        """Audio glue should return 400 when no files provided."""
        resp = self.app.post('/api/audio-glue')
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn('error', data)

    def test_metadata_extract_no_file(self):
        """Metadata extract should return 400 when no file."""
        resp = self.app.post('/api/metadata/extract')
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn('error', data)

    def test_metadata_apply_no_file(self):
        """Metadata apply should return 400 when no file."""
        resp = self.app.post('/api/metadata/apply')
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn('error', data)

    def test_document_to_epub_no_file(self):
        """Document to EPUB should return 400 when no file."""
        resp = self.app.post('/api/document-to-epub')
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn('error', data)

    def test_voices_endpoint(self):
        """Voices endpoint should return a list."""
        resp = self.app.get('/api/voices')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('voices', data)

    def test_metadata_lookup_empty(self):
        """Metadata lookup with empty body should return empty results."""
        resp = self.app.post('/api/metadata/lookup',
                             content_type='application/json',
                             data='{}')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['count'], 0)

    def test_index_serves_html(self):
        """Index route should serve HTML template."""
        resp = self.app.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'BPM4B', resp.data)


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

if __name__ == '__main__':
    # Run all tests
    unittest.main(verbosity=2)
