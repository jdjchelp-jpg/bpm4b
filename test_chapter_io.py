"""
Unit tests for bpm4b.chapter_io module.

Covers:
  - parse_cue_sheet()
  - parse_audacity_labels()
  - parse_webvtt()
  - parse_csv_chapters()
  - parse_json_chapters()
  - import_chapters() (auto-detect)
  - export_chapters() with all formats
  - get_supported_formats()
  - detect_format()
"""

import sys
import os
import tempfile
import json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import unittest
from bpm4b.chapter_io import (
    parse_cue_sheet,
    parse_audacity_labels,
    parse_webvtt,
    parse_csv_chapters,
    parse_json_chapters,
    import_chapters,
    export_chapters,
    get_supported_formats,
    detect_format,
    _write_vtt, _write_cue, _write_audacity, _write_csv, _write_json,
)


class TestParseCueSheet(unittest.TestCase):
    """Tests for parse_cue_sheet()"""

    def test_basic_cue(self):
        cue = '''TRACK 01 AUDIO
  TITLE "Chapter 1"
  INDEX 01 00:00:00
TRACK 02 AUDIO
  TITLE "Chapter 2"
  INDEX 01 03:45:30
TRACK 03 AUDIO
  TITLE "Chapter 3"
  INDEX 01 08:12:15
'''
        chapters = parse_cue_sheet(cue)
        self.assertEqual(len(chapters), 3)
        self.assertEqual(chapters[0]['title'], 'Chapter 1')
        self.assertEqual(chapters[0]['start_time'], 0.0)
        self.assertEqual(chapters[1]['title'], 'Chapter 2')
        # 3*60 + 45 + 30/75 = 225.4
        self.assertAlmostEqual(chapters[1]['start_time'], 225.4, places=1)
        self.assertAlmostEqual(chapters[2]['start_time'], 492.2, places=1)

    def test_empty_cue(self):
        chapters = parse_cue_sheet('')
        self.assertEqual(len(chapters), 0)

    def test_single_track(self):
        cue = '''TRACK 01 AUDIO
  TITLE "Single Chapter"
  INDEX 01 00:00:00
'''
        chapters = parse_cue_sheet(cue)
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0]['title'], 'Single Chapter')

    def test_dot_separator_time(self):
        # Dot separator (MM:SS.FF where FF = frames, 75 fps)
        # 01:30.00 = 1*60 + 30 + 0/75 = 90.0
        cue = '''TRACK 01 AUDIO
  TITLE "Test"
  INDEX 01 01:30.00
'''
        chapters = parse_cue_sheet(cue)
        self.assertEqual(chapters[0]['title'], 'Test')
        self.assertAlmostEqual(chapters[0]['start_time'], 90.0)


class TestParseAudacityLabels(unittest.TestCase):
    """Tests for parse_audacity_labels()"""

    def test_tab_separated(self):
        labels = "0.000\t300.500\tChapter 1\n300.500\t600.000\tChapter 2\n"
        chapters = parse_audacity_labels(labels)
        self.assertEqual(len(chapters), 2)
        self.assertEqual(chapters[0]['title'], 'Chapter 1')
        self.assertEqual(chapters[0]['start_time'], 0.0)
        self.assertAlmostEqual(chapters[0]['end_time'], 300.5)
        self.assertEqual(chapters[1]['title'], 'Chapter 2')

    def test_point_labels(self):
        """Point labels have start and end at the same time."""
        labels = "0.000\t\tIntro\n10.000\t\tSection 1\n"
        chapters = parse_audacity_labels(labels)
        self.assertEqual(len(chapters), 2)
        self.assertEqual(chapters[0]['title'], 'Intro')
        self.assertEqual(chapters[0]['start_time'], 0.0)

    def test_empty_lines(self):
        labels = "\n\n0.0\t10.0\tChapter 1\n\n\n"
        chapters = parse_audacity_labels(labels)
        self.assertEqual(len(chapters), 1)

    def test_comment_lines(self):
        labels = "# This is a comment\n0.0\t10.0\tChapter 1\n"
        chapters = parse_audacity_labels(labels)
        self.assertEqual(len(chapters), 1)

    def test_space_delimited(self):
        labels = "0 300 Chapter 1\n300 600 Chapter 2\n"
        chapters = parse_audacity_labels(labels)
        self.assertEqual(len(chapters), 2)
        self.assertEqual(chapters[0]['title'], 'Chapter 1')


class TestParseWebVTT(unittest.TestCase):
    """Tests for parse_webvtt()"""

    def test_basic_vtt(self):
        vtt = """WEBVTT

00:00:00.000 --> 00:03:45.500
Chapter 1 Title

00:03:45.500 --> 00:08:12.300
Chapter 2 Title
"""
        chapters = parse_webvtt(vtt)
        self.assertEqual(len(chapters), 2)
        self.assertEqual(chapters[0]['title'], 'Chapter 1 Title')
        self.assertEqual(chapters[0]['start_time'], 0.0)
        self.assertAlmostEqual(chapters[0]['end_time'], 225.5)
        self.assertEqual(chapters[1]['title'], 'Chapter 2 Title')

    def test_empty_vtt(self):
        chapters = parse_webvtt('')
        self.assertEqual(len(chapters), 0)

    def test_no_header(self):
        vtt = "00:00:00.000 --> 00:01:00.000\nIntro\n"
        chapters = parse_webvtt(vtt)
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0]['title'], 'Intro')


class TestParseCSVChapters(unittest.TestCase):
    """Tests for parse_csv_chapters()"""

    def test_basic_csv(self):
        csv_content = "Chapter 1,0,300\nChapter 2,300,600\n"
        chapters = parse_csv_chapters(csv_content)
        self.assertEqual(len(chapters), 2)
        self.assertEqual(chapters[0]['title'], 'Chapter 1')
        self.assertEqual(chapters[0]['start_time'], 0.0)
        self.assertEqual(chapters[0]['end_time'], 300.0)

    def test_without_end(self):
        csv_content = "Chapter 1,0\nChapter 2,300\n"
        chapters = parse_csv_chapters(csv_content)
        self.assertEqual(len(chapters), 2)
        # End times should be calculated

    def test_empty_csv(self):
        chapters = parse_csv_chapters('')
        self.assertEqual(len(chapters), 0)


class TestParseJSONChapters(unittest.TestCase):
    """Tests for parse_json_chapters()"""

    def test_list_format(self):
        data = [
            {'title': 'Chapter 1', 'start_time': 0, 'end_time': 300},
            {'title': 'Chapter 2', 'start_time': 300, 'end_time': 600},
        ]
        chapters = parse_json_chapters(json.dumps(data))
        self.assertEqual(len(chapters), 2)
        self.assertEqual(chapters[0]['title'], 'Chapter 1')

    def test_object_with_chapters_key(self):
        data = {'chapters': [
            {'title': 'Intro', 'start_time': 0, 'end_time': 60},
        ]}
        chapters = parse_json_chapters(json.dumps(data))
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0]['title'], 'Intro')

    def test_with_name_field(self):
        data = [{'name': 'My Chapter', 'start': 100, 'end': 200}]
        chapters = parse_json_chapters(json.dumps(data))
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0]['title'], 'My Chapter')

    def test_empty(self):
        chapters = parse_json_chapters('{}')
        self.assertEqual(len(chapters), 0)


class TestImportChapters(unittest.TestCase):
    """Tests for import_chapters() — auto-detect from files"""

    def create_temp_file(self, content, suffix):
        fd, path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, 'w') as f:
            f.write(content)
        return path

    def test_import_vtt(self):
        path = self.create_temp_file(
            "WEBVTT\n\n00:00:00.000 --> 00:01:00.000\nIntro\n",
            '.vtt'
        )
        try:
            chapters = import_chapters(path)
            self.assertEqual(len(chapters), 1)
            self.assertEqual(chapters[0]['title'], 'Intro')
        finally:
            os.remove(path)

    def test_import_cue(self):
        path = self.create_temp_file(
            'TRACK 01 AUDIO\n  TITLE "Test"\n  INDEX 01 00:00:00\n',
            '.cue'
        )
        try:
            chapters = import_chapters(path)
            self.assertEqual(len(chapters), 1)
            self.assertEqual(chapters[0]['title'], 'Test')
        finally:
            os.remove(path)

    def test_import_json(self):
        path = self.create_temp_file(
            json.dumps([{'title': 'Ch1', 'start_time': 0, 'end_time': 60}]),
            '.json'
        )
        try:
            chapters = import_chapters(path)
            self.assertEqual(len(chapters), 1)
            self.assertEqual(chapters[0]['title'], 'Ch1')
        finally:
            os.remove(path)

    def test_import_unsupported(self):
        path = self.create_temp_file("garbage", '.xyz')
        try:
            with self.assertRaises(ValueError):
                import_chapters(path)
        finally:
            os.remove(path)


class TestExportChapters(unittest.TestCase):
    """Tests for export_chapters()"""

    def setUp(self):
        self.chapters = [
            {'title': 'Chapter 1', 'start_time': 0.0, 'end_time': 300.5},
            {'title': 'Chapter 2', 'start_time': 300.5, 'end_time': 612.3},
        ]

    def test_export_vtt(self):
        content = _write_vtt(self.chapters)
        self.assertIn('WEBVTT', content)
        self.assertIn('Chapter 1', content)

    def test_export_cue(self):
        content = _write_cue(self.chapters)
        self.assertIn('TRACK 01 AUDIO', content)
        self.assertIn('Chapter 1', content)

    def test_export_audacity(self):
        content = _write_audacity(self.chapters)
        self.assertIn('Chapter 1', content)
        self.assertIn('0.000', content)

    def test_export_csv(self):
        content = _write_csv(self.chapters)
        self.assertIn('Chapter 1', content)
        self.assertIn('title', content)  # header

    def test_export_json(self):
        content = _write_json(self.chapters)
        data = json.loads(content)
        self.assertIn('chapters', data)
        self.assertEqual(len(data['chapters']), 2)

    def test_export_to_file(self):
        fd, path = tempfile.mkstemp(suffix='.vtt')
        os.close(fd)
        try:
            result = export_chapters(self.chapters, path, format='vtt')
            self.assertTrue(os.path.exists(result))
            with open(result) as f:
                content = f.read()
            self.assertIn('Chapter 1', content)
        finally:
            os.remove(path)

    def test_export_unsupported_format(self):
        with self.assertRaises(ValueError):
            export_chapters(self.chapters, '/dev/null', format='unsupported')


class TestHelpers(unittest.TestCase):
    """Tests for get_supported_formats() and detect_format()"""

    def test_get_supported_formats(self):
        fmts = get_supported_formats()
        self.assertIn('.cue', fmts)
        self.assertIn('.vtt', fmts)
        self.assertIn('.csv', fmts)
        self.assertIn('.json', fmts)
        self.assertIn('.txt', fmts)

    def test_detect_format(self):
        self.assertEqual(detect_format('file.cue'), '.cue')
        self.assertEqual(detect_format('file.vtt'), '.vtt')
        self.assertEqual(detect_format('file.csv'), '.csv')
        self.assertEqual(detect_format('file.json'), '.json')
        self.assertEqual(detect_format('file.txt'), '.txt')
        self.assertIsNone(detect_format('file.xyz'))
        self.assertIsNone(detect_format('file'))


if __name__ == '__main__':
    unittest.main()
