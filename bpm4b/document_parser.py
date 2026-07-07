"""
Document Parser Module
Extracts text and structural headings from PDF, DOCX, TXT, and EPUB files.
Ported from Node.js document-parser.js — uses modern pypdf instead of PyPDF2.
"""

import os
import re

try:
    from pypdf import PdfReader
except ImportError:
    try:
        from PyPDF2 import PdfReader  # ponytail: fallback for older installs
    except ImportError:
        PdfReader = None

try:
    import mammoth
except ImportError:
    mammoth = None

try:
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup
except ImportError:
    ebooklib = None

# Chapter heading patterns for plain-text detection
_CHAPTER_PATTERNS = [
    re.compile(
        r'^(chapter)\s+(\d+|[ivxlcdm]+|one|two|three|four|five|six|seven|eight|nine|ten'
        r'|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty'
        r'|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred)\b[\s:\-\u2013\u2014]*',
        re.IGNORECASE
    ),
    re.compile(r'^(part)\s+(\d+|[ivxlcdm]+|one|two|three|four|five|six|seven|eight|nine|ten)\b[\s:\-\u2013\u2014]*', re.IGNORECASE),
    re.compile(r'^(book)\s+(\d+|[ivxlcdm]+|one|two|three|four|five|six|seven|eight|nine|ten)\b[\s:\-\u2013\u2014]*', re.IGNORECASE),
    re.compile(r'^(section)\s+(\d+|[ivxlcdm]+)\b[\s:\-\u2013\u2014]*', re.IGNORECASE),
    re.compile(r'^(prologue|epilogue|introduction|preface|foreword|afterword|appendix)\b[\s:\-\u2013\u2014]*', re.IGNORECASE),
]


def parse_document(file_path):
    """
    Parse a document and extract text + heading structure.
    Returns: dict with 'text' and 'headings'
    """
    ext = os.path.splitext(file_path)[1].lower()
    parsers = {
        '.pdf': _parse_pdf,
        '.docx': _parse_docx,
        '.doc': _parse_docx,
        '.txt': _parse_txt,
        '.epub': _parse_epub,
        '.md': _parse_txt,
        '.markdown': _parse_txt,
    }
    if ext not in parsers:
        raise ValueError(f"Unsupported file format: {ext}. Supported: {', '.join(parsers)}")
    return parsers[ext](file_path)


def _parse_pdf(file_path):
    if PdfReader is None:
        raise ImportError("pypdf is required: pip install pypdf")
    reader = PdfReader(file_path)
    text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    return {'text': text, 'headings': _extract_headings_from_text(text)}


def _parse_docx(file_path):
    if mammoth is None:
        raise ImportError("mammoth is required: pip install mammoth")
    with open(file_path, 'rb') as f:
        buf = f.read()

    # HTML for heading detection
    import io
    html_result = mammoth.convert_to_html(io.BytesIO(buf))
    html = html_result.value or ''

    text_result = mammoth.extract_raw_text(io.BytesIO(buf))
    text = text_result.value or ''

    headings = []
    position = 0
    for m in re.finditer(r'<h([1-6])[^>]*>(.*?)</h[1-6]>', html, re.DOTALL | re.IGNORECASE):
        level = int(m.group(1))
        heading_text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        if heading_text:
            text_pos = text.find(heading_text, position)
            headings.append({
                'level': level,
                'text': heading_text,
                'position': text_pos if text_pos >= 0 else position
            })
            if text_pos >= 0:
                position = text_pos + len(heading_text)

    return {'text': text, 'headings': headings}


def _parse_txt(file_path):
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read()
    return {'text': text, 'headings': _extract_headings_from_text(text)}


def _parse_epub(file_path):
    if ebooklib is None:
        raise ImportError("ebooklib and beautifulsoup4 are required: pip install ebooklib beautifulsoup4")
    book = epub.read_epub(file_path)
    parts = []
    headings = []

    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            # Extract heading structure from HTML
            for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                heading_text = tag.get_text(strip=True)
                if heading_text:
                    level = int(tag.name[1])
                    # Position is approximate (char count so far)
                    approx_pos = sum(len(p) for p in parts)
                    headings.append({'level': level, 'text': heading_text, 'position': approx_pos})
            parts.append(soup.get_text(separator=' ', strip=False))

    text = '\n\n'.join(parts)
    if not headings:
        headings = _extract_headings_from_text(text)
    return {'text': text, 'headings': headings}


def _extract_headings_from_text(text):
    """Extract headings from plain text by detecting common chapter patterns."""
    headings = []
    char_pos = 0
    for line in text.split('\n'):
        stripped = line.strip()
        for pattern in _CHAPTER_PATTERNS:
            if pattern.match(stripped):
                lower = stripped.lower()
                level = 1 if (lower.startswith('part') or lower.startswith('book')) else 2
                headings.append({'level': level, 'text': stripped, 'position': char_pos})
                break
        char_pos += len(line) + 1
    return headings


def get_supported_formats():
    return ['.pdf', '.docx', '.doc', '.txt', '.epub', '.md', '.markdown']
