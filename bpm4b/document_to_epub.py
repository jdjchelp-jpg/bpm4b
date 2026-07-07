"""
Document to EPUB Converter
Converts various document formats (PDF, DOCX, TXT, MD, HTML, RTF) to EPUB.
Ported from Node.js v12 lib/document-to-epub.js
"""

import os
import re
import uuid
import logging
import tempfile
import zipfile
from xml.etree import ElementTree as ET
from datetime import datetime

from .document_parser import parse_document

logger = logging.getLogger(__name__)


def convert_to_epub(input_path, output_path, metadata=None):
    """
    Convert a document to EPUB format.

    Args:
        input_path: Path to source document
        output_path: Path for output EPUB file
        metadata: dict with optional keys: title, author, genre, description, language

    Returns:
        dict: {output_path, title, author, filename}
    """
    if metadata is None:
        metadata = {}

    # Parse the document first
    doc = parse_document(input_path)
    text = doc.get('text', '')
    headings = doc.get('headings', [])

    if not text or not text.strip():
        raise ValueError("No text content could be extracted from the document")

    title = metadata.get('title') or os.path.splitext(os.path.basename(input_path))[0]
    author = metadata.get('author') or 'Unknown'
    language = metadata.get('language', 'en')
    description = metadata.get('description', '')

    # Build EPUB structure
    book_id = str(uuid.uuid4())

    # Create temporary directory for EPUB contents
    work_dir = tempfile.mkdtemp(prefix='bpm4b_epub_')
    try:
        _build_epub(
            work_dir=work_dir,
            text=text,
            headings=headings,
            title=title,
            author=author,
            language=language,
            description=description,
            book_id=book_id,
        )

        # Package into EPUB (which is a ZIP file)
        _package_epub(work_dir, output_path)

        return {
            'output_path': output_path,
            'title': title,
            'author': author,
            'filename': os.path.basename(output_path),
        }

    finally:
        import shutil
        shutil.rmtree(work_dir, ignore_errors=True)


def _build_epub(work_dir, text, headings, title, author, language, description, book_id):
    """Build EPUB structure in working directory."""
    # Create META-INF
    meta_inf = os.path.join(work_dir, 'META-INF')
    os.makedirs(meta_inf, exist_ok=True)

    # container.xml
    container = ET.Element('container', {
        'version': '1.0',
        'xmlns': 'urn:oasis:names:tc:opendocument:xmlns:container',
    })
    rootfiles = ET.SubElement(container, 'rootfiles')
    rootfile = ET.SubElement(rootfiles, 'rootfile', {
        'full-path': 'OEBPS/content.opf',
        'media-type': 'application/oebps-package+xml',
    })
    _write_xml(os.path.join(meta_inf, 'container.xml'), container)

    # Create OEBPS
    oebps = os.path.join(work_dir, 'OEBPS')
    os.makedirs(oebps, exist_ok=True)

    # Split text into chapters based on headings
    chapters = _split_into_chapters(text, headings)

    # Write chapter XHTML files
    manifest_items = []
    spine_refs = []

    for i, chapter in enumerate(chapters):
        filename = f'chapter_{i+1:04d}.xhtml'
        filepath = os.path.join(oebps, filename)
        _write_chapter_xhtml(filepath, chapter['title'], chapter['content'], language)

        manifest_items.append({
            'id': f'chapter_{i+1}',
            'href': filename,
            'media-type': 'application/xhtml+xml',
        })
        spine_refs.append(f'chapter_{i+1}')

    # If no chapters were created, create one from all text
    if not chapters:
        filename = 'chapter_0001.xhtml'
        filepath = os.path.join(oebps, filename)
        _write_chapter_xhtml(filepath, title, text, language)
        manifest_items.append({
            'id': f'chapter_1',
            'href': filename,
            'media-type': 'application/xhtml+xml',
        })
        spine_refs.append(f'chapter_1')

    # style.css
    style = '''body { font-family: Georgia, 'Times New Roman', serif; line-height: 1.8; margin: 5%; }
h1 { text-align: center; font-size: 1.8em; margin: 2em 0 1em; }
h2 { font-size: 1.4em; margin: 1.5em 0 0.8em; }
p { text-indent: 1.5em; margin: 0.5em 0; }
.chapter-title { text-align: center; font-size: 2em; font-weight: bold; margin: 3em 0 2em; }
'''
    with open(os.path.join(oebps, 'style.css'), 'w', encoding='utf-8') as f:
        f.write(style)

    manifest_items.append({
        'id': 'css',
        'href': 'style.css',
        'media-type': 'text/css',
    })

    # content.opf
    opf = ET.Element('package', {
        'xmlns': 'http://www.idpf.org/2007/opf',
        'unique-identifier': 'bookid',
        'version': '3.0',
    })

    # metadata
    meta = ET.SubElement(opf, 'metadata', {
        'xmlns:dc': 'http://purl.org/dc/elements/1.1/',
        'xmlns:opf': 'http://www.idpf.org/2007/opf',
    })
    _add_meta(meta, 'dc:identifier', book_id, {'id': 'bookid'})
    _add_meta(meta, 'dc:title', title)
    _add_meta(meta, 'dc:creator', author, {'opf:role': 'aut'})
    _add_meta(meta, 'dc:language', language)
    if description:
        _add_meta(meta, 'dc:description', description)
    _add_meta(meta, 'dc:date', datetime.now().strftime('%Y-%m-%d'))

    # manifest
    manifest = ET.SubElement(opf, 'manifest')
    for item in manifest_items:
        ET.SubElement(manifest, 'item', item)

    # spine
    spine = ET.SubElement(opf, 'spine', {'toc': 'ncx'})
    for ref in spine_refs:
        ET.SubElement(spine, 'itemref', {'idref': ref})

    _write_xml(os.path.join(oebps, 'content.opf'), opf)

    # toc.ncx for EPUB 2 fallback
    ncx = ET.Element('ncx', {
        'xmlns': 'http://www.daisy.org/z3986/2005/ncx/',
        'version': '2005-1',
    })
    ncx_head = ET.SubElement(ncx, 'head')
    _add_meta(ncx_head, 'dtb:uid', book_id)
    _add_meta(ncx_head, 'dtb:depth', '1')
    _add_meta(ncx_head, 'dtb:totalPageCount', '0')
    _add_meta(ncx_head, 'dtb:maxPageNumber', '0')

    doc_title = ET.SubElement(ncx, 'docTitle')
    text_el = ET.SubElement(doc_title, 'text')
    text_el.text = title

    nav_map = ET.SubElement(ncx, 'navMap')
    for i, chapter in enumerate(chapters):
        nav_point = ET.SubElement(nav_map, 'navPoint', {
            'id': f'navPoint-{i+1}',
            'playOrder': str(i+1),
        })
        nav_label = ET.SubElement(nav_point, 'navLabel')
        nav_text = ET.SubElement(nav_label, 'text')
        nav_text.text = chapter['title']
        content = ET.SubElement(nav_point, 'content', {
            'src': f'chapter_{i+1:04d}.xhtml',
        })

    _write_xml(os.path.join(oebps, 'toc.ncx'), ncx)

    # Add mimetype file (must be first, uncompressed)
    with open(os.path.join(work_dir, 'mimetype'), 'w', encoding='utf-8') as f:
        f.write('application/epub+zip')


def _split_into_chapters(text, headings):
    """Split text into chapters using detected headings."""
    chapters = []

    if headings:
        for i, heading in enumerate(headings):
            next_heading = headings[i + 1] if i + 1 < len(headings) else None
            start_pos = heading['position']
            end_pos = next_heading['position'] if next_heading else len(text)
            content = text[start_pos:end_pos].strip()

            # Remove heading text from content if it starts with it
            if content.startswith(heading['text']):
                content = content[len(heading['text']):].strip()

            chapters.append({
                'title': heading['text'],
                'content': content,
            })

    # Fallback: detect chapter-like patterns in plain text
    if not chapters:
        chapter_pattern = re.compile(
            r'^(chapter|part|book|section)\s+\d+', re.IGNORECASE
        )
        lines = text.split('\n')
        chapter_starts = []
        for i, line in enumerate(lines):
            if chapter_pattern.match(line.strip()):
                chapter_starts.append(i)

        if len(chapter_starts) > 1:
            for i, start in enumerate(chapter_starts):
                end = chapter_starts[i + 1] if i + 1 < len(chapter_starts) else len(lines)
                chapter_lines = lines[start:end]
                title = chapter_lines[0].strip()
                content = '\n'.join(chapter_lines[1:]).strip()
                chapters.append({'title': title, 'content': content})

    return chapters


def _write_chapter_xhtml(filepath, title, content, language='en'):
    """Write a chapter as XHTML."""
    html = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{language}">
<head>
  <meta http-equiv="Content-Type" content="application/xhtml+xml; charset=utf-8"/>
  <link rel="stylesheet" type="text/css" href="style.css"/>
  <title>{_escape_xml(title)}</title>
</head>
<body>
  <h1 class="chapter-title">{_escape_xml(title)}</h1>
'''
    # Split content into paragraphs
    paragraphs = content.split('\n')
    for para in paragraphs:
        stripped = para.strip()
        if stripped:
            html += f'  <p>{_escape_xml(stripped)}</p>\n'

    html += '''</body>
</html>'''
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)


def _write_xml(filepath, element):
    """Write an ElementTree element as pretty XML."""
    tree = ET.ElementTree(element)
    tree.write(filepath, encoding='utf-8', xml_declaration=True)


def _add_meta(parent, name, value, attrs=None):
    """Add a metadata element to the parent."""
    elem = ET.SubElement(parent, name)
    if attrs:
        for k, v in attrs.items():
            elem.set(k, v)
    elem.text = value


def _escape_xml(text):
    """Escape text for XML output."""
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&apos;')
    return text


def _package_epub(work_dir, output_path):
    """Package the EPUB directory into a ZIP file with EPUB extension."""
    import shutil
    # Remove existing output if any
    if os.path.exists(output_path):
        os.remove(output_path)

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as epub_zip:
        # mimetype must be first, uncompressed
        mimetype_path = os.path.join(work_dir, 'mimetype')
        epub_zip.write(mimetype_path, 'mimetype', compress_type=zipfile.ZIP_STORED)

        for root, dirs, files in os.walk(work_dir):
            for file in files:
                file_path = os.path.join(root, file)
                if file == 'mimetype':
                    continue
                arcname = os.path.relpath(file_path, work_dir)
                epub_zip.write(file_path, arcname)


# Supported input formats for conversion
SUPPORTED_INPUT_FORMATS = [
    '.pdf', '.docx', '.doc', '.txt', '.md', '.markdown',
    '.html', '.htm', '.xhtml', '.rtf', '.odt', '.epub',
]
