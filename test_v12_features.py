"""
Unit tests for BPM4B v13 features (legacy test suite).
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _fake_subprocess_run_success(*args, **kwargs):
    class FakeResult:
        returncode = 0
        stdout = ''
        stderr = ''
    return FakeResult()


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
    """Test the ffmpeg availability check (v13 delegates to ffmpeg_utils)."""

    @mock.patch('bpm4b.ffmpeg_utils.find_ffmpeg')
    @mock.patch('bpm4b.ffmpeg_utils.subprocess.run')
    def test_ffmpeg_available(self, mock_run, mock_find):
        from bpm4b.core import check_ffmpeg
        mock_find.return_value = '/usr/bin/ffmpeg'
        mock_run.return_value = mock.MagicMock(returncode=0, stdout='ffmpeg version 7.0\n', stderr='')
        result = check_ffmpeg()
        self.assertTrue(result['available'])
        self.assertIn('ffmpeg version', result['version'])

    @mock.patch('bpm4b.ffmpeg_utils.find_ffmpeg', return_value=None)
    def test_ffmpeg_not_found(self, mock_find):
        from bpm4b.core import check_ffmpeg
        result = check_ffmpeg()
        self.assertFalse(result['available'])
        self.assertIsNotNone(result.get('error'))

    @mock.patch('bpm4b.ffmpeg_utils.find_ffmpeg', side_effect=Exception('Something broke'))
    def test_ffmpeg_unexpected_error(self, mock_find):
        from bpm4b.core import check_ffmpeg
        # The v13 get_ffmpeg_info() does not catch find_ffmpeg() exceptions
        with self.assertRaises(Exception):
            check_ffmpeg()


class TestGetAudioDuration(unittest.TestCase):
    """Test audio duration extraction (v13 delegates to ffmpeg_utils)."""

    @mock.patch('bpm4b.ffmpeg_utils.find_ffprobe')
    @mock.patch('bpm4b.ffmpeg_utils.subprocess.run')
    def test_ffprobe_duration(self, mock_run, mock_find):
        from bpm4b.core import get_audio_duration
        mock_find.return_value = '/usr/bin/ffprobe'
        mock_result = mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({'format': {'duration': '123.456'}})
        mock_run.return_value = mock_result
        duration = get_audio_duration('/fake/file.mp3')
        self.assertAlmostEqual(duration, 123.456)

    @mock.patch('bpm4b.ffmpeg_utils.find_ffmpeg', return_value='/usr/bin/ffmpeg')
    @mock.patch('bpm4b.ffmpeg_utils.find_ffprobe', return_value='/usr/bin/ffprobe')
    @mock.patch('bpm4b.ffmpeg_utils.subprocess.run')
    def test_ffmpeg_fallback_duration(self, mock_run, mock_find_probe, mock_find_ffmpeg):
        from bpm4b.core import get_audio_duration
        # Mock ffprobe call to fail, then ffmpeg fallback
        fail_result = mock.MagicMock()
        fail_result.returncode = 1
        fail_result.stdout = ''
        fail_result.stderr = 'error'
        ffmpeg_result = mock.MagicMock()
        ffmpeg_result.returncode = 0
        ffmpeg_result.stdout = ''
        ffmpeg_result.stderr = 'Duration: 00:05:30.50, start: ...'
        mock_run.side_effect = [fail_result, ffmpeg_result]
        duration = get_audio_duration('/fake/file.mp3')
        self.assertAlmostEqual(duration, 330.5, places=1)

    @mock.patch('bpm4b.ffmpeg_utils.find_ffmpeg', return_value='/usr/bin/ffmpeg')
    @mock.patch('bpm4b.ffmpeg_utils.find_ffprobe', return_value='/usr/bin/ffprobe')
    @mock.patch('bpm4b.ffmpeg_utils.subprocess.run')
    def test_wav_header_duration(self, mock_run, mock_find_probe, mock_find_ffmpeg):
        """v13 get_audio_duration falls back to ffmpeg stderr when ffprobe fails."""
        from bpm4b.core import get_audio_duration
        # First ffprobe call fails → falls through to ffmpeg stderr fallback
        fail_result = mock.MagicMock()
        fail_result.returncode = 1
        fail_result.stdout = ''
        fail_result.stderr = 'ffprobe error'
        ffmpeg_result = mock.MagicMock()
        ffmpeg_result.returncode = 0
        ffmpeg_result.stdout = ''
        ffmpeg_result.stderr = 'Duration: 00:00:01.00, start: 0.000000, bitrate: 384 kb/s'
        mock_run.side_effect = [fail_result, ffmpeg_result]
        duration = get_audio_duration('/fake/file.wav')
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
        with self.assertRaises(ValueError) as ctx:
            self.convert('/in.mp3', '/out.xyz', target_format='xyz')
        self.assertIn('Unsupported', str(ctx.exception))
        self.assertIn('xyz', str(ctx.exception))

    @mock.patch('bpm4b.core.subprocess.run')
    def test_mp3_conversion(self, mock_run):
        mock_run.return_value = _fake_subprocess_run_success()
        result = self.convert('/in.wav', '/out.mp3', target_format='mp3', quality='192k')
        self.assertEqual(result, '/out.mp3')
        cmd = mock_run.call_args[0][0]
        self.assertIn('libmp3lame', cmd)
        self.assertIn('192k', cmd)

    @mock.patch('bpm4b.core.subprocess.run')
    def test_wav_conversion(self, mock_run):
        mock_run.return_value = _fake_subprocess_run_success()
        result = self.convert('/in.mp3', '/out.wav', target_format='wav')
        self.assertEqual(result, '/out.wav')
        cmd = mock_run.call_args[0][0]
        self.assertIn('pcm_s16le', cmd)
        bitrate_args = [a for a in cmd if a in ('-b:a', '192k', '128k')]
        self.assertEqual(len(bitrate_args), 0)

    @mock.patch('bpm4b.core.subprocess.run')
    def test_flac_conversion(self, mock_run):
        mock_run.return_value = _fake_subprocess_run_success()
        result = self.convert('/in.mp3', '/out.flac', target_format='flac')
        self.assertEqual(result, '/out.flac')
        cmd = mock_run.call_args[0][0]
        self.assertIn('flac', cmd)
        bitrate_args = [a for a in cmd if a in ('-b:a',)]
        self.assertEqual(len(bitrate_args), 0)

    @mock.patch('bpm4b.core.subprocess.run')
    def test_aac_conversion(self, mock_run):
        mock_run.return_value = _fake_subprocess_run_success()
        result = self.convert('/in.mp3', '/out.aac', target_format='aac', quality='256k')
        self.assertEqual(result, '/out.aac')
        cmd = mock_run.call_args[0][0]
        self.assertIn('aac', cmd)
        self.assertIn('256k', cmd)

    @mock.patch('bpm4b.core.subprocess.run')
    def test_ogg_conversion(self, mock_run):
        mock_run.return_value = _fake_subprocess_run_success()
        result = self.convert('/in.mp3', '/out.ogg', target_format='ogg')
        self.assertEqual(result, '/out.ogg')
        cmd = mock_run.call_args[0][0]
        self.assertIn('libvorbis', cmd)

    @mock.patch('bpm4b.core.subprocess.run')
    def test_alac_conversion_adds_faststart(self, mock_run):
        mock_run.return_value = _fake_subprocess_run_success()
        result = self.convert('/in.mp3', '/out.m4a', target_format='alac')
        self.assertEqual(result, '/out.m4a')
        cmd = mock_run.call_args[0][0]
        self.assertIn('alac', cmd)
        self.assertIn('+faststart', ''.join(cmd))

    @mock.patch('bpm4b.core.subprocess.run')
    def test_extension_fix(self, mock_run):
        mock_run.return_value = _fake_subprocess_run_success()
        result = self.convert('/in.wav', '/out.wrong', target_format='mp3')
        self.assertTrue(result.endswith('.mp3'))
        self.assertIn('libmp3lame', mock_run.call_args[0][0])

    @mock.patch('bpm4b.core.subprocess.run')
    def test_ffmpeg_failure_propagates(self, mock_run):
        bad_result = mock.MagicMock()
        bad_result.returncode = 1
        bad_result.stderr = 'ffmpeg error: invalid data found'
        mock_run.return_value = bad_result
        with self.assertRaises(Exception) as ctx:
            self.convert('/in.mp3', '/out.mp3', target_format='mp3')
        self.assertIn('ffmpeg', str(ctx.exception).lower())


# ═══════════════════════════════════════════════════════════
# 3. Audio Glue (Batch Merge) — updated for v13 splice return
# ═══════════════════════════════════════════════════════════

class TestAudioGlue(unittest.TestCase):
    """Test the audio merge function (v13 returns dict from splice_audio_files)."""

    def setUp(self):
        from bpm4b.core import audio_glue
        self.glue = audio_glue

    def test_empty_input_raises(self):
        with self.assertRaises(ValueError):
            self.glue([], '/out.m4b')

    @mock.patch('bpm4b.splicer.find_ffmpeg')
    @mock.patch('bpm4b.splicer.subprocess.run')
    def test_single_input_accepted(self, mock_run, mock_find):
        mock_find.return_value = '/usr/bin/ffmpeg'
        mock_run.return_value = _fake_subprocess_run_success()
        result = self.glue(['/single.mp3'], '/out.m4b')
        # v13 returns a dict with output_path
        self.assertIsInstance(result, dict)
        self.assertEqual(result['output_path'], '/out.m4b')

    @mock.patch('bpm4b.splicer.find_ffmpeg')
    @mock.patch('bpm4b.ffmpeg_utils.find_ffprobe', return_value=None)
    @mock.patch('bpm4b.ffmpeg_utils.subprocess.run')
    def test_basic_merge(self, mock_run, mock_find_probe, mock_find):
        mock_find.return_value = '/usr/bin/ffmpeg'
        mock_run.return_value = _fake_subprocess_run_success()
        result = self.glue(['/a.mp3', '/b.mp3'], '/out.m4b', normalize=False)
        self.assertIsInstance(result, dict)

    @mock.patch('bpm4b.splicer.find_ffmpeg')
    @mock.patch('bpm4b.splicer.subprocess.run')
    def test_merge_with_normalize(self, mock_run, mock_find):
        mock_find.return_value = '/usr/bin/ffmpeg'
        # With normalize=True, multiple ffmpeg calls happen (per-file + final encode)
        mock_run.return_value = _fake_subprocess_run_success()
        self.glue(['/a.mp3', '/b.mp3'], '/out.m4b', normalize=True)
        # At least one call should include loudnorm
        all_calls = [args[0][0] for args in mock_run.call_args_list]
        has_loudnorm = any('loudnorm' in ' '.join(c) for c in all_calls)
        self.assertTrue(has_loudnorm or len(all_calls) > 1)

    @mock.patch('bpm4b.splicer.find_ffmpeg')
    @mock.patch('bpm4b.splicer.subprocess.run')
    def test_merge_with_volume(self, mock_run, mock_find):
        mock_find.return_value = '/usr/bin/ffmpeg'
        mock_run.return_value = _fake_subprocess_run_success()
        self.glue(['/a.mp3', '/b.mp3'], '/out.m4b', volume=1.5)
        # With volume != 1.0, we use the _splice_with_processing path which
        # converts to WAV first - so there should be multiple ffmpeg calls
        self.assertGreater(mock_run.call_count, 1)

    @mock.patch('bpm4b.splicer.find_ffmpeg')
    @mock.patch('bpm4b.splicer.subprocess.run')
    @mock.patch('bpm4b.core.tempfile.mkdtemp')
    def test_merge_cleanup_temp_files(self, mock_mkdtemp, mock_run, mock_find):
        mock_find.return_value = '/usr/bin/ffmpeg'
        mock_run.return_value = _fake_subprocess_run_success()
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_mkdtemp.return_value = os.path.join(tmpdir, 'work')
            os.makedirs(os.path.join(tmpdir, 'work'))
            a = os.path.join(tmpdir, 'a.mp3')
            b = os.path.join(tmpdir, 'b.mp3')
            with open(a, 'w') as f: f.write('')
            with open(b, 'w') as f: f.write('')
            out = os.path.join(tmpdir, 'out.m4b')
            self.glue([a, b], out)
            work_path = os.path.join(tmpdir, 'work')
            if os.path.exists(work_path):
                remaining = os.listdir(work_path)
                self.assertEqual(len(remaining), 0)

    @mock.patch('bpm4b.splicer.find_ffmpeg')
    @mock.patch('bpm4b.splicer.subprocess.run')
    def test_ffmpeg_error_propagates(self, mock_run, mock_find):
        mock_find.return_value = '/usr/bin/ffmpeg'
        bad_result = mock.MagicMock()
        bad_result.returncode = 1
        bad_result.stderr = 'concat error'
        mock_run.return_value = bad_result
        with self.assertRaises(Exception) as ctx:
            self.glue(['/a.mp3', '/b.mp3'], '/out.m4b')
        self.assertIn('splice', str(ctx.exception).lower())


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

    @mock.patch('bpm4b.metadata.subprocess.run')
    def test_extract_empty_metadata(self, mock_run):
        ffprobe_output = {'format': {'tags': {}, 'duration': '0'}, 'streams': []}
        mock_result = mock.MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(ffprobe_output)
        mock_run.return_value = mock_result
        meta = self.extract('/fake/file.m4b')
        self.assertEqual(meta['title'], '')
        self.assertEqual(meta['cover_base64'], None)

    @mock.patch('bpm4b.metadata.subprocess.run')
    def test_extract_ffprobe_error(self, mock_run):
        bad_result = mock.MagicMock()
        bad_result.returncode = 1
        bad_result.stderr = 'ffprobe error'
        mock_run.return_value = bad_result
        with self.assertRaises(Exception):
            self.extract('/fake/file.m4b')

    @mock.patch('bpm4b.metadata.subprocess.run')
    def test_extract_author_fallback(self, mock_run):
        ffprobe_output = {'format': {'tags': {'author': 'Jane Smith'}, 'duration': '100'}, 'streams': []}
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
        mock_run.return_value = _fake_subprocess_run_success()
        metadata = {'title': 'Test Book', 'author': 'Test Author', 'genre': 'Non-Fiction', 'description': 'A test'}
        result = self.apply('/in.m4b', '/out.m4b', metadata)
        self.assertTrue(result)
        cmd = mock_run.call_args[0][0]
        self.assertIn('-metadata', cmd)
        self.assertIn('title=Test Book', ''.join(cmd))
        self.assertIn('artist=Test Author', ''.join(cmd))

    @mock.patch('bpm4b.metadata.subprocess.run')
    def test_apply_with_cover(self, mock_run):
        mock_run.return_value = _fake_subprocess_run_success()
        metadata = {'title': 'Book'}
        cover_b64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
        result = self.apply('/in.m4b', '/out.m4b', metadata, cover_base64=cover_b64)
        self.assertTrue(result)

    @mock.patch('bpm4b.metadata.subprocess.run')
    def test_apply_empty_metadata(self, mock_run):
        mock_run.return_value = _fake_subprocess_run_success()
        result = self.apply('/in.m4b', '/out.m4b', {})
        self.assertTrue(result)
        cmd = mock_run.call_args[0][0]
        metadata_flags = [i for i, x in enumerate(cmd) if x == '-metadata']
        self.assertEqual(len(metadata_flags), 0)

    @mock.patch('bpm4b.metadata.subprocess.run')
    def test_apply_ffmpeg_error(self, mock_run):
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
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'docs': [{'title': 'The Great Gatsby', 'author_name': ['F. Scott Fitzgerald'], 'first_publish_year': 1925, 'publisher': ['Scribner'], 'isbn': ['9780743273565'], 'cover_i': 12345}]}
        mock_get.return_value = mock_response
        results = self.lookup(title='Great Gatsby')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], 'The Great Gatsby')

    @mock.patch('bpm4b.metadata.requests.get')
    def test_lookup_empty(self, mock_get):
        results = self.lookup()
        self.assertEqual(results, [])
        mock_get.assert_not_called()

    @mock.patch('bpm4b.metadata.requests.get')
    def test_lookup_no_results(self, mock_get):
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'docs': []}
        mock_get.return_value = mock_response
        results = self.lookup(title='xyzzy_nonexistent')
        self.assertEqual(results, [])

    @mock.patch('bpm4b.metadata.requests.get', side_effect=requests.exceptions.ConnectionError('Network error'))
    def test_lookup_network_error(self, mock_get):
        results = self.lookup(title='Test')
        self.assertEqual(results, [])


# ═══════════════════════════════════════════════════════════
# 5. Document to EPUB
# ═══════════════════════════════════════════════════════════

class TestConvertToEpub(unittest.TestCase):
    """Test document to EPUB conversion."""

    def _verify_epub_structure(self, epub_path):
        self.assertTrue(os.path.exists(epub_path))
        self.assertTrue(os.path.getsize(epub_path) > 100)
        with zipfile.ZipFile(epub_path, 'r') as z:
            names = z.namelist()
            self.assertIn('mimetype', names)
            self.assertIn('META-INF/container.xml', names)
            oebps_files = [n for n in names if n.startswith('OEBPS/')]
            self.assertGreater(len(oebps_files), 0)
            self.assertIn('OEBPS/content.opf', names)
            chapter_files = [n for n in names if n.startswith('OEBPS/chapter_')]
            self.assertGreater(len(chapter_files), 0)

    def test_txt_to_epub(self):
        from bpm4b.document_to_epub import convert_to_epub
        with tempfile.TemporaryDirectory() as tmpdir:
            txt_path = os.path.join(tmpdir, 'test_book.txt')
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write("This is a test paragraph.\n\nChapter 1\nFirst chapter text.\n\nChapter 2\nSecond chapter text.\n")
            epub_path = os.path.join(tmpdir, 'output.epub')
            result = convert_to_epub(txt_path, epub_path, {'title': 'Test Book', 'author': 'Test Author'})
            self.assertEqual(result['title'], 'Test Book')
            self.assertEqual(result['author'], 'Test Author')
            self._verify_epub_structure(epub_path)

    def test_txt_to_epub_no_headings(self):
        from bpm4b.document_to_epub import convert_to_epub
        with tempfile.TemporaryDirectory() as tmpdir:
            txt_path = os.path.join(tmpdir, 'plain.txt')
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write("Plain text without chapters. " * 20)
            epub_path = os.path.join(tmpdir, 'plain.epub')
            result = convert_to_epub(txt_path, epub_path)
            self._verify_epub_structure(epub_path)
            self.assertEqual(result['title'], 'plain')

    def test_epub_metadata_embedded(self):
        from bpm4b.document_to_epub import convert_to_epub
        with tempfile.TemporaryDirectory() as tmpdir:
            txt_path = os.path.join(tmpdir, 'meta_test.txt')
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write("Content for metadata test.\n" * 5)
            epub_path = os.path.join(tmpdir, 'meta_test.epub')
            convert_to_epub(txt_path, epub_path, {'title': 'Metadata Title', 'author': 'Metadata Author', 'language': 'fr'})
            with zipfile.ZipFile(epub_path, 'r') as z:
                opf_content = z.read('OEBPS/content.opf').decode('utf-8')
            self.assertIn('Metadata Title', opf_content)
            self.assertIn('Metadata Author', opf_content)

    def test_split_into_chapters_with_headings(self):
        from bpm4b.document_to_epub import _split_into_chapters
        text = "Intro text.\n\nChapter 1: The Beginning\nChapter one content.\n\nChapter 2: The Middle\nChapter two content.\n"
        headings = [{'text': 'Chapter 1: The Beginning', 'level': 2, 'position': 13}, {'text': 'Chapter 2: The Middle', 'level': 2, 'position': 62}]
        chapters = _split_into_chapters(text, headings)
        self.assertGreaterEqual(len(chapters), 2)

    def test_escape_xml(self):
        from bpm4b.document_to_epub import _escape_xml
        self.assertEqual(_escape_xml('AT&T'), 'AT&amp;T')
        self.assertEqual(_escape_xml('<hello>'), '&lt;hello&gt;')
        self.assertEqual(_escape_xml('"quoted"'), '&quot;quoted&quot;')

    def test_conversion_requires_text(self):
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
        mock_ffmpeg.return_value = {'available': True, 'version': 'ffmpeg 7.0'}
        resp = self.app.get('/api/health')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['version'], '13.0.0')
        self.assertTrue(data['ffmpeg']['available'])


class TestFlaskEndpoints(unittest.TestCase):
    """Test Flask API endpoint validation."""

    def setUp(self):
        from bpm4b.app import app
        self.app = app.test_client()

    def test_convert_no_file(self):
        resp = self.app.post('/api/convert')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('error', resp.get_json())

    def test_mp3_to_m4b_no_file(self):
        resp = self.app.post('/api/mp3-to-m4b')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('error', resp.get_json())

    def test_convert_audio_no_file(self):
        resp = self.app.post('/api/convert-audio')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('error', resp.get_json())

    def test_audio_glue_no_file(self):
        resp = self.app.post('/api/audio-glue')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('error', resp.get_json())

    def test_metadata_extract_no_file(self):
        resp = self.app.post('/api/metadata/extract')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('error', resp.get_json())

    def test_metadata_apply_no_file(self):
        resp = self.app.post('/api/metadata/apply')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('error', resp.get_json())

    def test_document_to_epub_no_file(self):
        resp = self.app.post('/api/document-to-epub')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('error', resp.get_json())

    def test_voices_endpoint(self):
        resp = self.app.get('/api/voices')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('voices', resp.get_json())

    def test_metadata_lookup_empty(self):
        resp = self.app.post('/api/metadata/lookup', content_type='application/json', data='{}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['count'], 0)

    def test_index_serves_html(self):
        resp = self.app.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'BPM4B', resp.data)


if __name__ == '__main__':
    unittest.main(verbosity=2)
