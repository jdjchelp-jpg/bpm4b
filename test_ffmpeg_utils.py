"""
Unit tests for bpm4b.ffmpeg_utils module.

Covers:
  - _format_bytes()
  - _format_duration()
  - _check_disk_space()
  - estimate_output_size() structure
  - estimate_batch_output_size() structure
  - get_ffmpeg_info() return structure
  - check_ffmpeg_compat() return structure
"""

import sys
import os
import tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import unittest
from unittest.mock import patch, MagicMock
from bpm4b.ffmpeg_utils import (
    _format_bytes,
    _format_duration,
    _check_disk_space,
    estimate_output_size,
    estimate_batch_output_size,
    get_ffmpeg_info,
    check_ffmpeg_compat,
    find_ffmpeg,
    find_ffprobe,
    get_audio_duration,
    get_audio_bitrate,
    get_sample_rate,
)


class TestFormatBytes(unittest.TestCase):
    """Tests for _format_bytes()"""

    def test_bytes(self):
        self.assertEqual(_format_bytes(0), '0 B')
        self.assertEqual(_format_bytes(500), '500 B')

    def test_kilobytes(self):
        self.assertEqual(_format_bytes(1024), '1.0 KB')
        self.assertEqual(_format_bytes(2048), '2.0 KB')
        self.assertEqual(_format_bytes(1536), '1.5 KB')

    def test_megabytes(self):
        self.assertEqual(_format_bytes(1048576), '1.0 MB')
        self.assertEqual(_format_bytes(5242880), '5.0 MB')

    def test_gigabytes(self):
        self.assertEqual(_format_bytes(1073741824), '1.0 GB')
        self.assertEqual(_format_bytes(5368709120), '5.0 GB')

    def test_terabytes(self):
        self.assertEqual(_format_bytes(1099511627776), '1.0 TB')

    def test_negative(self):
        # Bytes (< 1024) are formatted as integers, not floats
        self.assertEqual(_format_bytes(-1), '-1 B')


class TestFormatDuration(unittest.TestCase):
    """Tests for _format_duration()"""

    def test_seconds_only(self):
        self.assertEqual(_format_duration(30), '30s')
        self.assertEqual(_format_duration(5.5), '5s')

    def test_minutes_and_seconds(self):
        self.assertEqual(_format_duration(90), '1m 30s')
        self.assertEqual(_format_duration(150), '2m 30s')

    def test_hours(self):
        # Zero minutes are omitted: 1h 0m 0s → 1h 0s
        self.assertEqual(_format_duration(3600), '1h 0s')
        self.assertEqual(_format_duration(3661), '1h 1m 1s')
        self.assertEqual(_format_duration(9000), '2h 30m 0s')

    def test_zero(self):
        self.assertEqual(_format_duration(0), '0s')


class TestCheckDiskSpace(unittest.TestCase):
    """Tests for _check_disk_space()"""

    def test_sufficient_space(self):
        result = _check_disk_space(100)
        self.assertIsNone(result)

    def test_large_estimate(self):
        # An absurdly large value should trigger a warning
        result = _check_disk_space(10**30)
        self.assertIsNotNone(result)
        self.assertIn('Low disk space', result)


class TestEstimateOutputSize(unittest.TestCase):
    """Tests for estimate_output_size() structure"""

    @patch('bpm4b.ffmpeg_utils.get_audio_duration')
    def test_basic_estimate(self, mock_duration):
        mock_duration.return_value = 3600.0  # 1 hour
        result = estimate_output_size('test.mp3', target_bitrate_kbps=64, output_format='m4b')

        self.assertIn('input_path', result)
        self.assertIn('duration_seconds', result)
        self.assertIn('duration_human', result)
        self.assertIn('estimated_size_bytes', result)
        self.assertIn('estimated_size_human', result)
        self.assertIn('target_bitrate_kbps', result)
        self.assertIn('output_format', result)

        self.assertEqual(result['duration_seconds'], 3600.0)
        self.assertEqual(result['target_bitrate_kbps'], 64)
        self.assertEqual(result['output_format'], 'm4b')
        # 64 kbps * 1000 * 3600 sec / 8 = 28,800,000 bytes * 1.1 overhead = 31,680,000
        self.assertAlmostEqual(result['estimated_size_bytes'], 31680000, delta=1000)

    @patch('bpm4b.ffmpeg_utils.get_audio_duration')
    def test_higher_bitrate(self, mock_duration):
        mock_duration.return_value = 1800.0  # 30 min
        result = estimate_output_size('test.mp3', target_bitrate_kbps=128, output_format='mp3')

        # 128 * 1000 * 1800 / 8 = 28,800,000 * 1.1 = 31,680,000
        self.assertAlmostEqual(result['estimated_size_bytes'], 31680000, delta=1000)

    @patch('bpm4b.ffmpeg_utils.get_audio_duration')
    def test_zero_duration(self, mock_duration):
        mock_duration.return_value = 0.0
        result = estimate_output_size('test.mp3')
        self.assertIsNone(result['duration'])
        self.assertIsNone(result['estimated_size_bytes'])
        self.assertEqual(result['estimated_size_human'], 'Unknown')
        self.assertIn('error', result)

    @patch('bpm4b.ffmpeg_utils.get_audio_duration')
    def test_duration_human(self, mock_duration):
        mock_duration.return_value = 3661.0
        result = estimate_output_size('test.mp3')
        self.assertEqual(result['duration_human'], '1h 1m 1s')


class TestEstimateBatchOutputSize(unittest.TestCase):
    """Tests for estimate_batch_output_size()"""

    @patch('bpm4b.ffmpeg_utils.get_audio_duration')
    def test_multiple_files(self, mock_duration):
        mock_duration.return_value = 600.0  # 10 min each
        result = estimate_batch_output_size(
            ['file1.mp3', 'file2.mp3', 'file3.mp3'],
            target_bitrate_kbps=64, output_format='m4b'
        )
        self.assertIn('files', result)
        self.assertEqual(len(result['files']), 3)
        self.assertAlmostEqual(result['total_duration_seconds'], 1800.0)
        self.assertIn('total_duration_human', result)
        self.assertIn('total_estimated_size_bytes', result)
        self.assertIn('total_estimated_size_human', result)


class TestFFmpegInfo(unittest.TestCase):
    """Tests for get_ffmpeg_info() structure"""

    @patch('bpm4b.ffmpeg_utils.find_ffmpeg')
    @patch('bpm4b.ffmpeg_utils.subprocess.run')
    def test_ffmpeg_found(self, mock_run, mock_find):
        mock_find.return_value = '/usr/bin/ffmpeg'
        mock_run.return_value = MagicMock(returncode=0, stdout='ffmpeg version 6.0\n')

        result = get_ffmpeg_info()
        self.assertTrue(result['available'])
        self.assertEqual(result['path'], '/usr/bin/ffmpeg')
        self.assertIn('version', result)

    @patch('bpm4b.ffmpeg_utils.find_ffmpeg')
    def test_ffmpeg_not_found(self, mock_find):
        mock_find.return_value = None

        result = get_ffmpeg_info()
        self.assertFalse(result['available'])
        self.assertIsNone(result['path'])


class TestCheckFFmpegCompat(unittest.TestCase):
    """Tests for check_ffmpeg_compat() structure"""

    @patch('bpm4b.ffmpeg_utils.find_ffmpeg')
    def test_compat_not_available(self, mock_find):
        mock_find.return_value = None

        result = check_ffmpeg_compat()
        self.assertFalse(result['available'])
        # All feature flags should be False
        for key in ['concat_demuxer', 'silencedetect_filter', 'silenceremove_filter',
                     'aac_encoder', 'libmp3lame']:
            self.assertFalse(result.get(key, True), f"{key} should be False")


class TestFFmpegFindCache(unittest.TestCase):
    """Tests for find_ffmpeg() cache behavior"""

    def setUp(self):
        # Reset cache between tests
        import bpm4b.ffmpeg_utils
        bpm4b.ffmpeg_utils._FFMPEG_CACHE = None
        bpm4b.ffmpeg_utils._FFPROBE_CACHE = None

    @patch('shutil.which')
    def test_find_ffmpeg_via_shutil(self, mock_which):
        mock_which.return_value = '/usr/local/bin/ffmpeg'
        result = find_ffmpeg()
        self.assertEqual(result, '/usr/local/bin/ffmpeg')

    @patch('shutil.which')
    def test_find_ffprobe_via_shutil(self, mock_which):
        mock_which.return_value = '/usr/local/bin/ffprobe'
        result = find_ffprobe()
        self.assertEqual(result, '/usr/local/bin/ffprobe')


class TestGetAudioDuration(unittest.TestCase):
    """Tests for get_audio_duration()"""

    @patch('bpm4b.ffmpeg_utils.find_ffprobe')
    @patch('bpm4b.ffmpeg_utils.subprocess.run')
    def test_from_ffprobe(self, mock_run, mock_find):
        mock_find.return_value = '/usr/bin/ffprobe'
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"format": {"duration": "123.456"}}'
        mock_run.return_value = mock_result

        duration = get_audio_duration('test.mp3')
        self.assertAlmostEqual(duration, 123.456)

    @patch('bpm4b.ffmpeg_utils.find_ffprobe')
    def test_no_ffprobe(self, mock_find):
        mock_find.return_value = None
        duration = get_audio_duration('test.mp3')
        self.assertEqual(duration, 0.0)


class TestGetAudioBitrate(unittest.TestCase):
    """Tests for get_audio_bitrate()"""

    @patch('bpm4b.ffmpeg_utils.find_ffprobe')
    @patch('bpm4b.ffmpeg_utils.subprocess.run')
    def test_success(self, mock_run, mock_find):
        mock_find.return_value = '/usr/bin/ffprobe'
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"format": {"bit_rate": "128000"}}'
        mock_run.return_value = mock_result

        bitrate = get_audio_bitrate('test.mp3')
        self.assertEqual(bitrate, 128)

    @patch('bpm4b.ffmpeg_utils.find_ffprobe')
    def test_no_ffprobe(self, mock_find):
        mock_find.return_value = None
        bitrate = get_audio_bitrate('test.mp3')
        self.assertIsNone(bitrate)


class TestGetSampleRate(unittest.TestCase):
    """Tests for get_sample_rate()"""

    @patch('bpm4b.ffmpeg_utils.find_ffprobe')
    @patch('bpm4b.ffmpeg_utils.subprocess.run')
    def test_success(self, mock_run, mock_find):
        mock_find.return_value = '/usr/bin/ffprobe'
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"streams": [{"sample_rate": "44100"}]}'
        mock_run.return_value = mock_result

        sr = get_sample_rate('test.mp3')
        self.assertEqual(sr, 44100)

    @patch('bpm4b.ffmpeg_utils.find_ffprobe')
    def test_no_ffprobe(self, mock_find):
        mock_find.return_value = None
        sr = get_sample_rate('test.mp3')
        self.assertIsNone(sr)


if __name__ == '__main__':
    unittest.main()
