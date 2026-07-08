"""
Chapter Detector Module
Detects chapter boundaries from extracted document text,
extracts chapter names, and normalizes numbers to their word form.
Enhanced in v13 to delegate Roman numeral handling to text_processor.
Portions ported from Node.js chapter-detector.js
"""

import re

# Delegate Roman numeral and number handling to text_processor
from .text_processor import (
    roman_to_int,
    int_to_cardinal_words as int_to_words,
    normalize_chapter_title as normalize_title,
    resolve_roman_numerals_in_text,
)

WORD_TO_NUMBER = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
    'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
    'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20,
    'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60,
    'seventy': 70, 'eighty': 80, 'ninety': 90, 'hundred': 100,
}


def parse_chapter_number(num_str):
    """Parse a chapter number from digits, roman numerals, or words."""
    if not num_str:
        return None
    trimmed = num_str.strip().lower()
    if trimmed in WORD_TO_NUMBER:
        return WORD_TO_NUMBER[trimmed]
    try:
        return int(trimmed)
    except ValueError:
        pass
    if re.match(r'^[ivxlcdm]+$', trimmed, re.I):
        val = roman_to_int(trimmed)
        if val > 0:
            return val
    return None


# Regex patterns
_CHAPTER_PATTERN = re.compile(
    r'^(chapter)\s+(\d+|[ivxlcdm]+|one|two|three|four|five|six|seven|eight|nine|ten'
    r'|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty'
    r'|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred)\b[\s:\-\u2013\u2014]*(.*)?$',
    re.IGNORECASE
)
_SPECIAL_PATTERN = re.compile(
    r'^(prologue|epilogue|introduction|preface|foreword|afterword|appendix)\b[\s:\-\u2013\u2014]*(.*)?$',
    re.IGNORECASE
)


def detect_chapters(text, headings=None):
    """
    Detect chapters from extracted text and headings.

    Returns list of dicts: [{number, title, content}]
    """
    if headings is None:
        headings = []

    chapters = []
    if headings:
        chapters = _build_chapters_from_headings(text, headings)

    if not chapters:
        chapters = _build_chapters_from_text(text)

    if not chapters:
        chapters = [{
            'number': 1,
            'title': 'Full Text',
            'content': normalize_numbers_in_text(clean_body_text(text))
        }]

    return chapters


def _build_chapters_from_headings(text, headings):
    chapters = []
    for i, heading in enumerate(headings):
        next_heading = headings[i + 1] if i + 1 < len(headings) else None
        start_pos = heading['position']
        end_pos = next_heading['position'] if next_heading else len(text)
        content = text[start_pos:end_pos].strip()

        heading_line = heading['text']
        if content.startswith(heading_line):
            content = content[len(heading_line):].strip()

        chapter_num = _extract_chapter_number_from_heading(heading['text'])
        title = _extract_chapter_title(heading['text'], content)

        chapters.append({
            'number': chapter_num,
            'title': title,
            'content': normalize_numbers_in_text(clean_body_text(content))
        })
    return chapters


def _build_chapters_from_text(text):
    chapters = []
    lines = text.split('\n')
    boundaries = []
    char_pos = 0

    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        m = _CHAPTER_PATTERN.match(line)
        if m:
            boundaries.append({
                'line_index': i,
                'position': char_pos,
                'number': parse_chapter_number(m.group(2)),
                'inline_title': (m.group(3) or '').strip(),
                'heading_text': line,
            })
        else:
            m2 = _SPECIAL_PATTERN.match(line)
            if m2:
                last = boundaries[-1] if boundaries else None
                too_close = last and (i - last['line_index']) <= 2
                if not too_close:
                    inline = (m2.group(2) or '').strip()
                    boundaries.append({
                        'line_index': i,
                        'position': char_pos,
                        'number': None,
                        'inline_title': inline or m2.group(1),
                        'heading_text': line,
                    })
        char_pos += len(raw_line) + 1

    if not boundaries:
        return []

    for i, boundary in enumerate(boundaries):
        next_b = boundaries[i + 1] if i + 1 < len(boundaries) else None
        start_pos = boundary['position']
        end_pos = next_b['position'] if next_b else len(text)
        content = text[start_pos:end_pos].strip()

        if content.startswith(boundary['heading_text']):
            content = content[len(boundary['heading_text']):].strip()

        title = boundary['inline_title']
        if not title:
            title = _extract_subtitle_from_content(content)
        if not title:
            title = boundary['heading_text']

        chapters.append({
            'number': boundary['number'],
            'title': title,
            'content': normalize_numbers_in_text(clean_body_text(content))
        })

    return chapters


def _extract_chapter_number_from_heading(heading_text):
    m = re.search(r'(?:chapter|part|book|section)\s+(\S+)', heading_text, re.I)
    if m:
        return parse_chapter_number(m.group(1))
    return None


def _extract_chapter_title(heading_text, content):
    m = re.search(r'(?:chapter|part|book|section)\s+\S+[\s:\-\u2013\u2014]+(.+)', heading_text, re.I)
    if m and m.group(1).strip():
        return m.group(1).strip()

    m2 = re.match(r'^(prologue|epilogue|introduction|preface|foreword|afterword|appendix)[\s:\-\u2013\u2014]*(.*)', heading_text, re.I)
    if m2:
        return m2.group(2).strip() or m2.group(1).strip()

    subtitle = _extract_subtitle_from_content(content)
    if subtitle:
        return subtitle

    return heading_text


def _extract_subtitle_from_content(content):
    lines = content.split('\n')
    for line in lines[:3]:
        line = line.strip()
        if line and 0 < len(line) < 100 and not line.endswith('.'):
            return line
    return None


def clean_body_text(text):
    """Remove page numbers and excessive whitespace."""
    text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def normalize_numbers_in_text(text):
    """Convert standalone integers to word form for TTS (e.g., 7 → seven)."""
    def replacer(m):
        num = int(m.group(1))
        if num > 9999:
            return m.group(0)
        try:
            return int_to_words(num)
        except Exception:
            return m.group(0)
    return re.sub(r'\b(\d+)\b', replacer, text)
