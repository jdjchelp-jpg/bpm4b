"""
Unit tests for bpm4b.cover_art module.

Covers:
  - extract_chapters_from_m4b() response parsing
  - write_chapters_to_m4b() metadata generation
  - inherit_metadata_from_first_file()
  - _read_file_tags()
  - sync_chapters_to_mp3() sidecar creation
"""

import sys
import os
import json
import tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import unittest
from unittest.mock import patch, MagicMock, mock_open
from bpm4b.cover_art import (
    extract_chapters_from_m4b,
    write_chapters_to_m4b,
    sync_chapters_to_mp3,
    inherit_metadata_from_first_file,
    extract_cover_art,
    inject_cover_art,
    inject_cover_from_base64,
    _read_file_tags,
)


class TestExtractChaptersFromM4b(unittest.TestCase):
    """Tests for extract_chapters_from_m4b()"""

    @patch('bpm4b.cover_art.find_ffprobe')
    @patch('bpm4b.cover_art.subprocess.run')
    def test_extract_simple_chapters(self, mock_run, mock_find):
        mock_find.return_value = '/usr/bin/ffprobe'
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            'chapters': [
                {
                    'id': 0, 'time_base': '1/1000',
                    'start': 0, 'start_time': 0.0,
                    'end': 300000, 'end_time': 300.0,
                    'metadata': {'title': 'Chapter 1'},
                },
                {
                    'id': 1, 'time_base': '1/1000',
                    'start': 300000, 'start_time': 300.0,
                    'end': 600000, 'end_time': 600.0,
                    'metadata': {'title': 'Chapter 2'},
                },
            ]
        })
        mock_run.return_value = mock_result

        chapters = extract_chapters_from_m4b('test.m4b')
        self.assertEqual(len(chapters), 2)
        self.assertEqual(chapters[0]['title'], 'Chapter 1')
        self.assertAlmostEqual(chapters[0]['start_time'], 0.0)
        self.assertAlmostEqual(chapters[0]['end_time'], 300.0)
        self.assertEqual(chapters[1]['title'], 'Chapter 2')

    @patch('bpm4b.cover_art.find_ffprobe')
    @patch('bpm4b.cover_art.subprocess.run')
    def test_extract_no_chapters(self, mock_run, mock_find):
        mock_find.return_value = '/usr/bin/ffprobe'
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({'chapters': []})
        mock_run.return_value = mock_result

        chapters = extract_chapters_from_m4b('test.m4b')
        self.assertEqual(len(chapters), 0)

    @patch('bpm4b.cover_art.find_ffprobe')
    @patch('bpm4b.cover_art.subprocess.run')
    def test_extract_via_tags_fallback(self, mock_run, mock_find):
        """Some files use 'tags' instead of 'metadata'."""
        mock_find.return_value = '/usr/bin/ffprobe'
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            'chapters': [
                {
                    'id': 0, 'time_base': '1/1000',
                    'start': 0, 'end': 100000,
                    'start_time': 0.0, 'end_time': 100.0,
                    'tags': {'title': 'The Beginning'},
                },
            ]
        })
        mock_run.return_value = mock_result

        chapters = extract_chapters_from_m4b('test.m4b')
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0]['title'], 'The Beginning')

    @patch('bpm4b.cover_art.find_ffprobe')
    def test_no_ffprobe(self, mock_find):
        mock_find.return_value = None
        with self.assertRaises(RuntimeError):
            extract_chapters_from_m4b('test.m4b')


class TestWriteChaptersToM4b(unittest.TestCase):
    """Tests for write_chapters_to_m4b()"""

    @patch('bpm4b.cover_art.find_ffmpeg')
    @patch('bpm4b.cover_art.subprocess.run')
    @patch('uuid.uuid4')
    def test_chapter_metadata_format(self, mock_uuid, mock_run, mock_find):
        mock_find.return_value = '/usr/bin/ffmpeg'
        mock_uuid.return_value = MagicMock(hex='abcdef12')
        mock_run.return_value = MagicMock(returncode=0)

        chapters = [
            {'title': 'Chapter 1', 'start_time': 0.0, 'end_time': 300.5},
            {'title': 'Chapter 2', 'start_time': 300.5, 'end_time': 612.3},
        ]

        # Patch built-in open and os.path.exists
        with patch('builtins.open', mock_open()) as mock_file:
            with patch('os.path.exists', return_value=True):
                with patch('os.remove'):
                    result = write_chapters_to_m4b('input.m4b', 'output.m4b', chapters)
                    self.assertEqual(result, 'output.m4b')

                    # Verify chapter file was written with correct format
                    handle = mock_file()
                    written_content = ''.join(call[0][0] for call in handle.write.call_args_list)
                    self.assertIn(';FFMETADATA1', written_content)
                    self.assertIn('[CHAPTER]', written_content)
                    self.assertIn('TIMEBASE=1/1000', written_content)
                    self.assertIn('START=0', written_content)
                    self.assertIn('END=300500', written_content)
                    self.assertIn('title=Chapter 1', written_content)
                    self.assertIn('START=300500', written_content)
                    self.assertIn('END=612300', written_content)

    @patch('bpm4b.cover_art.find_ffmpeg')
    def test_no_ffmpeg(self, mock_find):
        mock_find.return_value = None
        with self.assertRaises(RuntimeError):
            write_chapters_to_m4b('in.m4b', 'out.m4b', [])


class TestSyncChaptersToMp3(unittest.TestCase):
    """Tests for sync_chapters_to_mp3()"""

    @patch('bpm4b.cover_art.find_ffprobe')
    @patch('bpm4b.cover_art.subprocess.run')
    def test_sync_creates_sidecars(self, mock_run, mock_find):
        mock_find.return_value = '/usr/bin/ffprobe'
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            'chapters': [
                {'id': 0, 'time_base': '1/1000', 'start': 0, 'end': 100000,
                 'start_time': 0.0, 'end_time': 100.0,
                 'metadata': {'title': 'Ch1'}},
            ]
        })
        mock_run.return_value = mock_result

        with patch('builtins.open', mock_open()):
            with patch('os.path.splitext', return_value=('/tmp/test', '.mp3')):
                with patch('os.remove'):
                    result = sync_chapters_to_mp3('test.m4b', ['/tmp/test.mp3'], '/tmp')
                    self.assertEqual(len(result), 1)
                    self.assertEqual(result[0]['chapter']['title'], 'Ch1')

    @patch('bpm4b.cover_art.find_ffprobe')
    @patch('bpm4b.cover_art.subprocess.run')
    def test_sync_no_chapters(self, mock_run, mock_find):
        mock_find.return_value = '/usr/bin/ffprobe'
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({'chapters': []})
        mock_run.return_value = mock_result

        result = sync_chapters_to_mp3('test.m4b', ['/tmp/test.mp3'], '/tmp')
        self.assertEqual(len(result), 0)


class TestInheritMetadata(unittest.TestCase):
    """Tests for inherit_metadata_from_first_file()"""

    @patch('bpm4b.cover_art._read_file_tags')
    def test_basic_inheritance(self, mock_read):
        mock_read.return_value = {
            'title': 'My Book',
            'author': 'John Doe',
            'genre': 'Fiction',
        }

        result = inherit_metadata_from_first_file(
            ['/path/first.mp3', '/path/second.mp3']
        )
        self.assertEqual(result['title'], 'My Book')
        self.assertEqual(result['author'], 'John Doe')
        self.assertEqual(result['genre'], 'Fiction')

    @patch('bpm4b.cover_art._read_file_tags')
    def test_existing_metadata_overrides(self, mock_read):
        mock_read.return_value = {
            'title': 'Original Title',
            'author': 'Original Author',
        }

        result = inherit_metadata_from_first_file(
            ['/path/first.mp3'],
            metadata={'title': 'Override Title'}
        )
        self.assertEqual(result['title'], 'Override Title')
        self.assertEqual(result['author'], 'Original Author')

    @patch('bpm4b.cover_art._read_file_tags')
    def test_empty_file_list(self, mock_read):
        result = inherit_metadata_from_first_file([])
        self.assertEqual(result, {})

    @patch('bpm4b.cover_art._read_file_tags')
    def test_metadata_only_no_files(self, mock_read):
        result = inherit_metadata_from_first_file([], metadata={'manual': 'data'})
        self.assertEqual(result, {'manual': 'data'})


class TestReadFileTags(unittest.TestCase):
    """Tests for _read_file_tags()"""

    @patch('bpm4b.cover_art.find_ffprobe')
    @patch('bpm4b.cover_art.subprocess.run')
    def test_read_tags_success(self, mock_run, mock_find):
        mock_find.return_value = '/usr/bin/ffprobe'
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            'format': {
                'tags': {
                    'title': 'Test Book',
                    'artist': 'Test Author',
                    'genre': 'Non-fiction',
                    'album': 'My Album',
                    'date': '2024',
                }
            }
        })
        mock_run.return_value = mock_result

        tags = _read_file_tags('test.mp3')
        self.assertEqual(tags['title'], 'Test Book')
        self.assertEqual(tags['author'], 'Test Author')
        self.assertEqual(tags['genre'], 'Non-fiction')
        self.assertEqual(tags['album'], 'My Album')
        self.assertEqual(tags['date'], '2024')

    @patch('bpm4b.cover_art.find_ffprobe')
    def test_no_ffprobe(self, mock_find):
        mock_find.return_value = None
        tags = _read_file_tags('test.mp3')
        self.assertEqual(tags, {})

    @patch('bpm4b.cover_art.find_ffprobe')
    @patch('bpm4b.cover_art.subprocess.run')
    def test_no_tags(self, mock_run, mock_find):
        mock_find.return_value = '/usr/bin/ffprobe'
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({'format': {}})
        mock_run.return_value = mock_result

        tags = _read_file_tags('test.mp3')
        self.assertEqual(tags['title'], '')
        self.assertEqual(tags['author'], '')


class TestExtractCoverArt(unittest.TestCase):
    """Tests for extract_cover_art() — structure and error handling"""

    @patch('bpm4b.cover_art.find_ffmpeg')
    @patch('bpm4b.cover_art.find_ffprobe')
    @patch('bpm4b.cover_art.subprocess.run')
    def test_extract_no_cover_stream(self, mock_run, mock_find_probe, mock_find_ffmpeg):
        mock_find_ffmpeg.return_value = '/usr/bin/ffmpeg'
        mock_find_probe.return_value = '/usr/bin/ffprobe'

        # First subprocess.run call is for probing (returns no video stream)
        def side_effect(cmd, **kwargs):
            if 'ffprobe' in cmd[0]:
                return MagicMock(
                    returncode=0,
                    stdout=json.dumps({'streams': [{'codec_type': 'audio'}]})
                )
            return MagicMock(returncode=0)

        mock_run.side_effect = side_effect

        result = extract_cover_art('test.m4b')
        self.assertIsNone(result)

    @patch('bpm4b.cover_art.find_ffmpeg')
    def test_no_ffmpeg(self, mock_find):
        mock_find.return_value = None
        with self.assertRaises(RuntimeError):
            extract_cover_art('test.m4b')


class TestInjectCoverArt(unittest.TestCase):
    """Tests for inject_cover_art()"""

    @patch('bpm4b.cover_art.find_ffmpeg')
    @patch('bpm4b.cover_art.subprocess.run')
    @patch('os.path.isfile')
    def test_inject_jpeg(self, mock_isfile, mock_run, mock_find):
        mock_find.return_value = '/usr/bin/ffmpeg'
        mock_isfile.return_value = True
        mock_run.return_value = MagicMock(returncode=0)

        with patch('os.path.splitext', return_value=('/path/cover', '.jpg')):
            result = inject_cover_art('audio.m4b', 'cover.jpg', 'output.m4b')
            self.assertEqual(result, 'output.m4b')

    @patch('bpm4b.cover_art.find_ffmpeg')
    def test_cover_not_found(self, mock_find):
        mock_find.return_value = '/usr/bin/ffmpeg'
        with self.assertRaises(FileNotFoundError):
            inject_cover_art('audio.m4b', 'nonexistent.jpg', 'output.m4b')

    @patch('bpm4b.cover_art.find_ffmpeg')
    @patch('os.path.isfile')
    def test_unsupported_format(self, mock_isfile, mock_find):
        mock_find.return_value = '/usr/bin/ffmpeg'
        mock_isfile.return_value = True
        with patch('os.path.splitext', return_value=('/path/cover', '.gif')):
            with self.assertRaises(ValueError):
                inject_cover_art('audio.m4b', 'cover.gif', 'output.m4b')


class TestInjectCoverFromBase64(unittest.TestCase):
    """Tests for inject_cover_from_base64()"""

    @patch('bpm4b.cover_art.inject_cover_art')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists', return_value=True)
    @patch('os.remove')
    def test_inject_jpeg_base64(self, mock_remove, mock_exists, mock_open_file, mock_inject):
        mock_inject.return_value = 'output.m4b'
        import base64
        # A tiny valid JPEG (minimal)
        jpeg_bytes = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08\x01\x00\x01\x00\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x11\x04\x12!1A\x06\x13Qa\x07"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&\'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xc4\x00\x1f\x01\x01\x01\x01\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x11\x00\x02\x01\x02\x04\x04\x03\x04\x07\x05\x04\x04\x00\x01\x02\x77\x00\x01\x02\x03\x11\x04\x05!1\x06\x12Q\x13AQa\x07"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&\'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xb5\xc0\xff\xd9'
        b64 = base64.b64encode(jpeg_bytes).decode('ascii')

        result = inject_cover_from_base64('audio.m4b', b64, 'output.m4b')
        self.assertEqual(result, 'output.m4b')


if __name__ == '__main__':
    unittest.main()
