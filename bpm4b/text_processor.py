"""
Smart Roman Numeral Resolver & LitRPG Stat Block Compactor

Features:
  #2  - Smart Roman Numeral Resolver (context-aware IV→4 conversion)
  #3  - LitRPG Stat Block Compactors
  #14 - Smart Roman Numeral Chapter Formatter (regex normalization)
"""

import re
import os
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# #2 & #14: Roman Numeral Handling
# ═══════════════════════════════════════════════════════════════

ROMAN_MAP = {
    'I': 1, 'V': 5, 'X': 10, 'L': 50,
    'C': 100, 'D': 500, 'M': 1000,
}

# Anchor words that signal a Roman numeral should be converted
ROMAN_ANCHOR_WORDS = {
    'chapter', 'ch', 'chap', 'volume', 'vol', 'book', 'part',
    'section', 'act', 'scene', 'king', 'queen', 'prince',
    'princess', 'emperor', 'empress', 'pope', 'pope',
    'henry', 'edward', 'george', 'richard', 'louis',
    'charles', 'james', 'william', 'elizabeth', 'catherine',
    'mary', 'anne', 'victoria', 'alexander', 'nicholas',
    'appendix', 'annex', 'exhibit',
}

# Roman numerals that are also common English words (false positive check)
ROMAN_FALSE_POSITIVES = {
    'I',     # pronoun "I"
    'II',    # can be part of names like "John II"
    'III',   # medical term, names
    'IV',    # IV (intravenous)
    'V',     # letter V
    'VI',    # can appear in names
    'D',     # letter D
    'C',     # letter C / programming language
    'M',     # letter M
    'L',     # letter L
    'X',     # letter X
    'LI',    # can be part of words
    'DI',    # can be part of words
}

# Known non-chapter Roman numeral uses (in context)
NON_CHAPTER_CONTEXTS = [
    r'\b(?:world\s+war|ww)\s*(i|ii)\b',
    r'\b(?:type|model|mark|class|grade)\s+[ivxlcdm]+\b',
    r'\b[ivxlcdm]+\s*(?:times?|fold)\b',
    r'\bchapter\s+\d+\b.*?\b[ivxlcdm]+\b',
]


def roman_to_int(roman: str) -> int:
    """Convert a Roman numeral string to an integer."""
    if not roman or not re.match(r'^[IVXLCDM]+$', roman, re.I):
        return 0

    upper = roman.upper()
    total = 0
    for i, ch in enumerate(upper):
        current = ROMAN_MAP.get(ch, 0)
        nxt = ROMAN_MAP.get(upper[i + 1], 0) if i + 1 < len(upper) else 0
        total += current if current >= nxt else -current
    return total


def int_to_ordinal_words(n: int) -> str:
    """Convert an integer to its ordinal word form (e.g., 4 → 'fourth')."""
    cardinal_map = {
        1: 'first', 2: 'second', 3: 'third', 4: 'fourth',
        5: 'fifth', 6: 'sixth', 7: 'seventh', 8: 'eighth',
        9: 'ninth', 10: 'tenth', 11: 'eleventh', 12: 'twelfth',
        13: 'thirteenth', 14: 'fourteenth', 15: 'fifteenth',
        16: 'sixteenth', 17: 'seventeenth', 18: 'eighteenth',
        19: 'nineteenth', 20: 'twentieth',
    }
    if n in cardinal_map:
        return cardinal_map[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        if tens == 0:
            return f'{ones}th'
        tens_map = {2: 'twentieth', 3: 'thirtieth', 4: 'fortieth',
                    5: 'fiftieth', 6: 'sixtieth', 7: 'seventieth',
                    8: 'eightieth', 9: 'ninetieth'}
        if ones == 0:
            return tens_map.get(tens, f'{tens}0th')
        # e.g. 22 → "twenty-second"
        unit_map = {1: 'first', 2: 'second', 3: 'third', 4: 'fourth',
                    5: 'fifth', 6: 'sixth', 7: 'seventh', 8: 'eighth', 9: 'ninth'}
        tens_word_map = {2: 'twenty', 3: 'thirty', 4: 'forty', 5: 'fifty',
                         6: 'sixty', 7: 'seventy', 8: 'eighty', 9: 'ninety'}
        return f'{tens_word_map[tens]}-{unit_map[ones]}'
    return f'{n}th'


def int_to_cardinal_words(n: int) -> str:
    """Convert an integer to its cardinal word form (e.g., 4 → 'four')."""
    cardinal_map = {
        0: 'zero', 1: 'one', 2: 'two', 3: 'three', 4: 'four',
        5: 'five', 6: 'six', 7: 'seven', 8: 'eight', 9: 'nine',
        10: 'ten', 11: 'eleven', 12: 'twelve', 13: 'thirteen',
        14: 'fourteen', 15: 'fifteen', 16: 'sixteen', 17: 'seventeen',
        18: 'eighteen', 19: 'nineteen', 20: 'twenty',
    }
    if n in cardinal_map:
        return cardinal_map[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        tens_map = {2: 'twenty', 3: 'thirty', 4: 'forty', 5: 'fifty',
                    6: 'sixty', 7: 'seventy', 8: 'eighty', 9: 'ninety'}
        if ones == 0:
            return tens_map[tens]
        return f'{tens_map[tens]}-{cardinal_map[ones]}'
    if n < 1000:
        h, rest = divmod(n, 100)
        base = f'{cardinal_map[h]} hundred'
        return base if rest == 0 else f'{base} {int_to_cardinal_words(rest)}'
    if n < 1000000:
        t, rest = divmod(n, 1000)
        base = f'{int_to_cardinal_words(t)} thousand'
        return base if rest == 0 else f'{base} {int_to_cardinal_words(rest)}'
    return str(n)


# ─── Context-Aware Roman Numeral Resolution ──────────────────

def _is_in_chapter_context(text: str, pos: int, roman: str) -> bool:
    """
    Determine if a Roman numeral at position `pos` in `text` is likely
    a chapter/volume/section number (as opposed to a pronoun, letter, etc.).

    Uses lookahead/lookbehind for anchor words.
    """
    # Check context window (~50 chars before and ~20 chars after)
    start = max(0, pos - 60)
    end = min(len(text), pos + len(roman) + 40)
    context = text[start:end].lower()

    # Check if near anchor words
    for anchor in ROMAN_ANCHOR_WORDS:
        if anchor in context:
            return True

    # Check for leading number patterns like "Chapter 5 Section II"
    preceding = text[max(0, pos - 30):pos].lower()
    if re.search(r'(?:chapter|part|section|volume|book)\s*\d+\s+', preceding):
        return True

    # Check for Roman numeral patterns in running text
    if re.search(r'\b(?:volumes?|chapters?|sections?|parts?)\s+i[ivxlcdm]*\b', context):
        return True

    return False


def _is_non_chapter_context(text: str, pos: int, roman: str) -> bool:
    """Check if Roman numeral is in a known non-chapter context."""
    start = max(0, pos - 40)
    end = min(len(text), pos + len(roman) + 40)
    context = text[start:end].lower()
    for pattern in NON_CHAPTER_CONTEXTS:
        if re.search(pattern, context):
            return True
    return False


def resolve_roman_numerals_in_text(text: str, mode: str = 'ordinal') -> str:
    """
    Smart Roman Numeral Resolver — converts Roman numerals to words
    when contextually appropriate (near chapter/volume/part anchors).

    Args:
        text: Input text
        mode: 'ordinal' → 'Chapter IV' becomes 'Chapter fourth'
              'cardinal' → 'Chapter IV' becomes 'Chapter four'

    Returns:
        Text with resolved Roman numerals
    """
    if mode == 'ordinal':
        converter = int_to_ordinal_words
    else:
        converter = int_to_cardinal_words

    result = []
    last_end = 0

    # Find all Roman numeral candidates
    for m in re.finditer(r'\b[IVXLCDM]+\b', text):
        roman = m.group()
        pos = m.start()

        # Skip single-letter Roman numerals unless in chapter context
        if len(roman) == 1 and roman not in ('I', 'V', 'X'):
            continue

        # Skip if it looks like part of a larger word boundary issue
        if len(roman) == 1 and m.start() > 0 and text[m.start() - 1].isalpha():
            continue

        val = roman_to_int(roman)
        if val <= 0 or val > 1000:
            continue

        # Check non-chapter contexts first
        if _is_non_chapter_context(text, pos, roman):
            result.append(text[last_end:m.end()])
            last_end = m.end()
            continue

        # Only convert if in a chapter-like context
        if _is_in_chapter_context(text, pos, roman):
            word = converter(val)
            result.append(text[last_end:pos])
            result.append(word)
            last_end = m.end()

    result.append(text[last_end:])
    return ''.join(result)


# ─── Chapter Title Normalization (Pattern-Based) ─────────────

def normalize_chapter_title(title: str) -> str:
    """
    Normalize a chapter title to a standard format.

    Examples:
      "Ch. I"       → "Chapter 1"
      "CHAPTER 1"   → "Chapter 1"
      "ch_01"       → "Chapter 1"
      "Chapter III" → "Chapter 3"
      "Chap. XII"   → "Chapter 12"
    """
    original = title.strip()
    if not original:
        return original

    # Pattern: (Ch|Chap|Chapter|Ch\.|Chap\.) (number|roman)
    pattern = re.compile(
        r'^(ch(?:ap(?:ter)?)?\.?)\s*'
        r'(\d+|[ivxlcdm]+)'
        r'\b[\s:\-\u2013\u2014]*(.*)$',
        re.IGNORECASE
    )
    m = pattern.match(original)
    if m:
        num_str = m.group(2)
        rest = (m.group(3) or '').strip()

        # Try as number
        try:
            num = int(num_str)
        except ValueError:
            # Try as Roman numeral
            num = roman_to_int(num_str)

        if num and num > 0:
            base = f'Chapter {num}'
            return f'{base}: {rest}' if rest else base

    # Pattern: ch_01, ch01, ch-01 (underscore/dash/hyphen separators)
    pattern2 = re.compile(r'^ch[_\-\s]*(\d+)$', re.IGNORECASE)
    m2 = pattern2.match(original)
    if m2:
        return f'Chapter {int(m2.group(1))}'

    # Pattern: part_i, book_iii, sec_v
    pattern3 = re.compile(
        r'^(part|book|section|volume)[_\-\s]*(\d+|[ivxlcdm]+)$', re.IGNORECASE
    )
    m3 = pattern3.match(original)
    if m3:
        prefix = m3.group(1).capitalize()
        num_str = m3.group(2)
        try:
            num = int(num_str)
        except ValueError:
            num = roman_to_int(num_str)
        if num and num > 0:
            return f'{prefix} {num}'
        return f'{prefix} {num_str.upper()}'

    return original


def normalize_all_chapter_titles(chapters: List[Dict]) -> List[Dict]:
    """
    Normalize chapter titles in a list of chapter dicts.
    Expected format: [{title, content, ...}]
    """
    normalized = []
    for ch in chapters:
        ch = dict(ch)
        ch['title'] = normalize_chapter_title(ch.get('title', ''))
        normalized.append(ch)
    return normalized


# ─── Filename / Manifest Chapter Normalization ───────────────

def normalize_chapter_filename(filename: str) -> Optional[Dict]:
    """
    Parse and normalize a filename that represents a chapter.
    Returns dict with {title, number} or None if not recognizable.

    Examples:
      "Chapter_01_The_Beginning.mp3" → {title: "Chapter 1: The Beginning", number: 1}
      "ch_12.mp3" → {title: "Chapter 12", number: 12}
      "CHAPTER III - War.mp3" → {title: "Chapter 3: War", number: 3}
    """
    name = os.path.splitext(filename)[0] if '.' in filename else filename
    name = name.replace('_', ' ').replace('-', ' ').replace('.', ' ')

    # Try chapter patterns
    pattern = re.compile(
        r'(?:ch(?:ap(?:ter)?)?\.?\s*)'
        r'(\d+|[ivxlcdm]+)'
        r'(?:[\s:\-_\u2013\u2014]+(.*))?',
        re.IGNORECASE
    )
    m = pattern.match(name.strip())
    if m:
        num_str = m.group(1)
        try:
            num = int(num_str)
        except ValueError:
            num = roman_to_int(num_str)

        rest = (m.group(2) or '').strip()
        title = f'Chapter {num}'
        if rest:
            rest_clean = re.sub(r'^[\s\-_]+', '', rest)
            if rest_clean:
                title = f'{title}: {rest_clean}'
        return {'title': title, 'number': num}

    return None


# ═══════════════════════════════════════════════════════════════
# #3: LitRPG Stat Block Compactors
# ═══════════════════════════════════════════════════════════════

# Patterns that indicate the start of a stat block
STAT_BLOCK_START_PATTERNS = [
    re.compile(r'^(?:name|level|class|race|title|rank|hp|mp|mana|health|stamina|stats?|attributes?|abilities?|skills?|powers?|traits?|perks?)\s*[:\-]', re.IGNORECASE),
    re.compile(r'^(?:strength|agility|dexterity|constitution|intelligence|wisdom|charisma|endurance|vitality|willpower|perception|luck)\s*[:\-]', re.IGNORECASE),
    re.compile(r'^(?:str|agi|dex|con|int|wis|cha|end|vit|wil|per|lck)\s*[:\-]', re.IGNORECASE),
    re.compile(r'^(?:health|mana|stamina)\s*[:\-]', re.IGNORECASE),
    re.compile(r'^(?:hit\s*points?|skill\s*points?|experience|exp|xp|level\s*\d+)\s*[:\-]', re.IGNORECASE),
]

# Individual stat lines
STAT_LINE_PATTERN = re.compile(
    r'^\s*'                                       # leading whitespace
    r'(?:[-•·*▶✧✦]+)?\s*'                         # optional bullet markers
    r'((?:str|agi|dex|con|int|wis|cha|end|vil|per|lck|'
    r'strength|agility|dexterity|constitution|'
    r'intelligence|wisdom|charisma|endurance|vitality|'
    r'willpower|perception|luck|'
    r'health|mana|stamina|hp|mp|sp|'
    r'attack|defense|defence|speed|armor|armour|'
    r'damage|critical|crit|dodge|block|parry|resist|'
    r'skill|skill\s*points?|ability|talent|perk|trait|'
    r'stat\s*points?|exp|experience|level|x))\s*'  # stat name
    r'[:\-+=]\s*'                                  # separator
    r'(\d+(?:\.\d+)?(?:\s*[+\-]\s*\d+)?)'          # value with optional modifier
    r'(?:\s*\(.*?\))?'                             # optional parenthetical
    r'$',
    re.IGNORECASE
)


def detect_stat_blocks(text: str) -> List[Dict]:
    """
    Detect LitRPG stat blocks in text.

    Returns list of dicts with:
      start, end (char positions), lines (list of stat lines), summary
    """
    lines = text.split('\n')
    blocks = []
    current_block = None

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip empty lines - they can separate blocks
        if not stripped:
            if current_block and len(current_block['stat_lines']) >= 3:
                # Finalize block
                blocks.append(_finalize_stat_block(current_block))
                current_block = None
            continue

        # Check for stat block start
        is_start = any(p.match(stripped) for p in STAT_BLOCK_START_PATTERNS)
        is_stat_line = bool(STAT_LINE_PATTERN.match(stripped))

        # If this line is both a start marker AND a stat line, prefer stat line behavior
        if is_stat_line and current_block is not None:
            # Add to current block as a stat line
            current_block['stat_lines'].append(stripped)
            current_block['raw_lines'].append(line)
        elif is_start:
            # Start a new block (or restart if previous had enough lines)
            if current_block and len(current_block['stat_lines']) >= 3:
                blocks.append(_finalize_stat_block(current_block))
            current_block = {
                'start_line': i,
                'start_char': sum(len(lines[j]) + 1 for j in range(i)),
                'stat_lines': [stripped],
                'raw_lines': [line],
            }
        elif is_stat_line and current_block is None:
            # First stat line — start a new block
            current_block = {
                'start_line': i,
                'start_char': sum(len(lines[j]) + 1 for j in range(i)),
                'stat_lines': [stripped],
                'raw_lines': [line],
            }
        elif current_block and len(current_block['stat_lines']) >= 3:
            # Non-stat line after detection — finalize
            blocks.append(_finalize_stat_block(current_block))
            current_block = None

    # Finalize any remaining block
    if current_block and len(current_block['stat_lines']) >= 3:
        blocks.append(_finalize_stat_block(current_block))

    return blocks


def _finalize_stat_block(block: Dict) -> Dict:
    """Finalize a detected stat block with summary."""
    stat_lines = block['raw_lines']
    end_line = block['start_line'] + len(stat_lines)
    end_char = block['start_char'] + sum(len(l) + 1 for l in stat_lines)

    # Parse stats
    stats = {}
    for line in stat_lines:
        m = STAT_LINE_PATTERN.match(line)
        if m:
            name = m.group(1).strip()
            value = m.group(2).strip()
            stats[name.lower()] = value

    # Generate summary
    stat_items = [f'{k.title()}: {v}' for k, v in stats.items()]
    if len(stat_items) > 4:
        summary = f'[Stats: {", ".join(stat_items[:4])} +{len(stat_items) - 4} more]'
    else:
        summary = f'[Stats: {", ".join(stat_items)}]'

    return {
        'start_char': block['start_char'],
        'end_char': end_char,
        'stat_lines': stat_lines,
        'parsed_stats': stats,
        'summary': summary,
        'stat_count': len(stats),
    }


def compact_stat_blocks(text: str, mode: str = 'summarize') -> str:
    """
    Process LitRPG stat blocks in text.

    Args:
        text: Input text
        mode:
          'summarize' → Replace stat blocks with a short summary
          'skip'      → Remove stat blocks entirely
          'keep'      → Leave unchanged (pass-through)
          'flag'      → Wrap stat blocks in markers for TTS special handling

    Returns:
        Processed text
    """
    if mode == 'keep':
        return text

    blocks = detect_stat_blocks(text)
    if not blocks:
        return text

    result_parts = []
    last_end = 0

    for block in blocks:
        # Text before this block
        result_parts.append(text[last_end:block['start_char']])

        if mode == 'skip':
            result_parts.append('')
        elif mode == 'summarize':
            result_parts.append(f"\n{block['summary']}\n")
        elif mode == 'flag':
            result_parts.append(f"\n<STATBLOCK>{block['summary']}</STATBLOCK>\n")

        last_end = block['end_char']

    result_parts.append(text[last_end:])
    return ''.join(result_parts)


def stat_block_word_count(text: str) -> int:
    """Count the number of words in detected stat blocks."""
    blocks = detect_stat_blocks(text)
    total = 0
    for block in blocks:
        for line in block['stat_lines']:
            total += len(line.split())
    return total


# ─── File-system level normalization ─────────────────────────
# normalize_chapter_filename uses os.path.splitext which is already imported at top
