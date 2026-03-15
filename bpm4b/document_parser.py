import os
import mammoth
from PyPDF2 import PdfReader
try:
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup
except ImportError:
    ebooklib = None

def parse_document(file_path):
    """
    Parse document and extract text and basic headings.
    Returns: dict with 'text' and 'headings'
    """
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.pdf':
        return parse_pdf(file_path)
    elif ext == '.docx':
        return parse_docx(file_path)
    elif ext == '.epub':
        return parse_epub(file_path)
    elif ext == '.txt':
        return parse_txt(file_path)
    else:
        raise ValueError(f"Unsupported file extension: {ext}")

def parse_pdf(file_path):
    reader = PdfReader(file_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return {"text": text, "headings": []}

def parse_docx(file_path):
    with open(file_path, "rb") as docx_file:
        result = mammoth.convert_to_text(docx_file)
        return {"text": result.value, "headings": []}

def parse_txt(file_path):
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        return {"text": f.read(), "headings": []}

def parse_epub(file_path):
    if not ebooklib:
        raise ImportError("ebooklib and beautifulsoup4 are required for EPUB support")
    
    book = epub.read_epub(file_path)
    text = []
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            text.append(soup.get_text())
            
    return {"text": "\n".join(text), "headings": []}
