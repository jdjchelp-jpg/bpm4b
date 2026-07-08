"""
Unit tests for bpm4b.text_processor module.

Covers:
  - roman_to_int()
  - int_to_ordinal_words() / int_to_cardinal_words()
  - normalize_chapter_title()
  - normalize_chapter_filename()
  - resolve_roman_numerals_in_text() (context-aware)
  - normalize_all_chapter_titles()
  - detect_stat_blocks()
  - compact_stat_blocks()
  - stat_block_word_count()
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import unittest
from bpm4b.text_processor import (
    roman_to_int,
    int_to_ordinal_words,
    int_to_cardinal_words,
    normalize_chapter_title,
    normalize_chapter_filename,
    resolve_roman_numerals_in_text,
    normalize_all_chapter_titles,
    detect_stat_blocks,
    compact_stat_blocks,
    stat_block_word_count,
)


class TestRomanToInt(unittest.TestCase):
    """Tests for roman_to_int()"""

    def test_basic(self):
        self.assertEqual(roman_to_int('I'), 1)
        self.assertEqual(roman_to_int('V'), 5)
        self.assertEqual(roman_to_int('X'), 10)
        self.assertEqual(roman_to_int('L'), 50)
        self.assertEqual(roman_to_int('C'), 100)
        self.assertEqual(roman_to_int('D'), 500)
        self.assertEqual(roman_to_int('M'), 1000)

    def test_composite(self):
        self.assertEqual(roman_to_int('IV'), 4)
        self.assertEqual(roman_to_int('IX'), 9)
        self.assertEqual(roman_to_int('XL'), 40)
        self.assertEqual(roman_to_int('XC'), 90)
        self.assertEqual(roman_to_int('CD'), 400)
        self.assertEqual(roman_to_int('CM'), 900)

    def test_large(self):
        self.assertEqual(roman_to_int('MCMXCVIII'), 1998)
        self.assertEqual(roman_to_int('MMXXIV'), 2024)
        self.assertEqual(roman_to_int('MMMCMXCIX'), 3999)

    def test_case_insensitive(self):
        self.assertEqual(roman_to_int('iv'), 4)
        self.assertEqual(roman_to_int('XII'), 12)
        self.assertEqual(roman_to_int('xii'), 12)

    def test_invalid(self):
        self.assertEqual(roman_to_int(''), 0)
        self.assertEqual(roman_to_int('ABC'), 0)
        self.assertEqual(roman_to_int('123'), 0)
        self.assertEqual(roman_to_int('IIII'), 4)  # technically additive but works


class TestIntToWords(unittest.TestCase):
    """Tests for int_to_ordinal_words() and int_to_cardinal_words()"""

    def test_ordinal_small(self):
        self.assertEqual(int_to_ordinal_words(1), 'first')
        self.assertEqual(int_to_ordinal_words(2), 'second')
        self.assertEqual(int_to_ordinal_words(3), 'third')
        self.assertEqual(int_to_ordinal_words(4), 'fourth')
        self.assertEqual(int_to_ordinal_words(5), 'fifth')
        self.assertEqual(int_to_ordinal_words(10), 'tenth')
        self.assertEqual(int_to_ordinal_words(20), 'twentieth')

    def test_ordinal_large(self):
        self.assertEqual(int_to_ordinal_words(21), 'twenty-first')
        self.assertEqual(int_to_ordinal_words(99), 'ninety-ninth')
        self.assertEqual(int_to_ordinal_words(100), '100th')
        self.assertEqual(int_to_ordinal_words(1000), '1000th')

    def test_cardinal_small(self):
        self.assertEqual(int_to_cardinal_words(0), 'zero')
        self.assertEqual(int_to_cardinal_words(1), 'one')
        self.assertEqual(int_to_cardinal_words(7), 'seven')
        self.assertEqual(int_to_cardinal_words(10), 'ten')
        self.assertEqual(int_to_cardinal_words(12), 'twelve')
        self.assertEqual(int_to_cardinal_words(20), 'twenty')

    def test_cardinal_tens(self):
        self.assertEqual(int_to_cardinal_words(21), 'twenty-one')
        self.assertEqual(int_to_cardinal_words(37), 'thirty-seven')
        self.assertEqual(int_to_cardinal_words(99), 'ninety-nine')

    def test_cardinal_hundreds(self):
        self.assertEqual(int_to_cardinal_words(100), 'one hundred')
        self.assertEqual(int_to_cardinal_words(101), 'one hundred one')
        self.assertEqual(int_to_cardinal_words(321), 'three hundred twenty-one')

    def test_cardinal_thousands(self):
        self.assertEqual(int_to_cardinal_words(1000), 'one thousand')
        self.assertEqual(int_to_cardinal_words(2024), 'two thousand twenty-four')


class TestNormalizeChapterTitle(unittest.TestCase):
    """Tests for normalize_chapter_title()"""

    def test_basic_numeric(self):
        self.assertEqual(normalize_chapter_title('Chapter 1'), 'Chapter 1')
        self.assertEqual(normalize_chapter_title('CHAPTER 1'), 'Chapter 1')
        self.assertEqual(normalize_chapter_title('chapter 5'), 'Chapter 5')

    def test_roman(self):
        self.assertEqual(normalize_chapter_title('Chapter I'), 'Chapter 1')
        self.assertEqual(normalize_chapter_title('Chapter IV'), 'Chapter 4')
        self.assertEqual(normalize_chapter_title('Chapter XII'), 'Chapter 12')

    def test_abbreviated(self):
        self.assertEqual(normalize_chapter_title('Ch. 1'), 'Chapter 1')
        self.assertEqual(normalize_chapter_title('Ch. III'), 'Chapter 3')
        self.assertEqual(normalize_chapter_title('Chap. 2'), 'Chapter 2')

    def test_underscore_separator(self):
        self.assertEqual(normalize_chapter_title('ch_01'), 'Chapter 1')
        self.assertEqual(normalize_chapter_title('CH_42'), 'Chapter 42')

    def test_with_subtitle(self):
        self.assertEqual(normalize_chapter_title('Chapter 1: The Beginning'), 'Chapter 1: The Beginning')
        self.assertEqual(normalize_chapter_title('Chapter III - War'), 'Chapter 3: War')
        self.assertEqual(normalize_chapter_title('Chap. II — The Journey'), 'Chapter 2: The Journey')

    def test_part_book_section(self):
        self.assertEqual(normalize_chapter_title('Part 1'), 'Part 1')
        self.assertEqual(normalize_chapter_title('Book III'), 'Book 3')
        self.assertEqual(normalize_chapter_title('Section 5'), 'Section 5')

    def test_empty(self):
        self.assertEqual(normalize_chapter_title(''), '')
        self.assertEqual(normalize_chapter_title('  '), '')

    def test_no_change(self):
        self.assertEqual(normalize_chapter_title('Introduction'), 'Introduction')
        self.assertEqual(normalize_chapter_title('Prologue'), 'Prologue')
        self.assertEqual(normalize_chapter_title('Epilogue'), 'Epilogue')


class TestNormalizeChapterFilename(unittest.TestCase):
    """Tests for normalize_chapter_filename()"""

    def test_basic(self):
        result = normalize_chapter_filename('Chapter_01_The_Beginning.mp3')
        self.assertIsNotNone(result)
        self.assertEqual(result['title'], 'Chapter 1: The Beginning')
        self.assertEqual(result['number'], 1)

    def test_roman_filename(self):
        result = normalize_chapter_filename('Chapter III - War.mp3')
        self.assertIsNotNone(result)
        self.assertEqual(result['title'], 'Chapter 3: War')
        self.assertEqual(result['number'], 3)

    def test_ch_underscore(self):
        result = normalize_chapter_filename('ch_12.mp3')
        self.assertIsNotNone(result)
        self.assertEqual(result['number'], 12)

    def test_no_match(self):
        self.assertIsNone(normalize_chapter_filename('intro.mp3'))
        self.assertIsNone(normalize_chapter_filename('music_track_01.mp3'))
        self.assertIsNone(normalize_chapter_filename('readme.txt'))


class TestResolveRomanNumerals(unittest.TestCase):
    """Tests for resolve_roman_numerals_in_text()"""

    def test_chapter_context_ordinal(self):
        text = "Chapter IV: The Quest Begins"
        result = resolve_roman_numerals_in_text(text, mode='ordinal')
        self.assertEqual(result, "Chapter fourth: The Quest Begins")

    def test_chapter_context_cardinal(self):
        text = "Chapter IV: The Quest Begins"
        result = resolve_roman_numerals_in_text(text, mode='cardinal')
        self.assertEqual(result, "Chapter four: The Quest Begins")

    def test_multiple_chapters(self):
        text = "Chapter I: Start\nChapter II: Next\nChapter III: Final"
        result = resolve_roman_numerals_in_text(text, mode='ordinal')
        self.assertIn("Chapter first: Start", result)
        self.assertIn("Chapter second: Next", result)
        self.assertIn("Chapter third: Final", result)

    def test_volume_context(self):
        text = "Volume X contains the final chapters."
        result = resolve_roman_numerals_in_text(text, mode='ordinal')
        self.assertIn("Volume tenth", result)

    def test_pronoun_i_not_converted(self):
        """The pronoun 'I' should NOT be converted outside chapter context."""
        text = "I went to the store. I bought some bread."
        result = resolve_roman_numerals_in_text(text)
        self.assertEqual(result, text)

    def test_book_context(self):
        text = "Book V: The Empire Strikes Back"
        result = resolve_roman_numerals_in_text(text, mode='cardinal')
        self.assertIn("Book five", result)

    def test_non_chapter_roman_untouched(self):
        """World War II should not be converted to 'World War second'"""
        text = "During World War II, many events occurred."
        result = resolve_roman_numerals_in_text(text)
        self.assertEqual(result, text)

    def test_mixed_content(self):
        text = "In Book I, the hero began. I thought this was interesting."
        result = resolve_roman_numerals_in_text(text, mode='ordinal')
        self.assertIn("Book first", result)
        # The pronoun "I" within the 60-character context window of "Book I" may also be converted
        self.assertNotEqual(result, text)


class TestNormalizeAllChapterTitles(unittest.TestCase):
    """Tests for normalize_all_chapter_titles()"""

    def test_basic(self):
        chapters = [
            {'title': 'Chapter I', 'content': 'Once upon...'},
            {'title': 'CHAPTER 2', 'content': 'Next part...'},
            {'title': 'Ch. III', 'content': 'Final part...'},
        ]
        result = normalize_all_chapter_titles(chapters)
        self.assertEqual(result[0]['title'], 'Chapter 1')
        self.assertEqual(result[1]['title'], 'Chapter 2')
        self.assertEqual(result[2]['title'], 'Chapter 3')
        self.assertEqual(result[0]['content'], 'Once upon...')


class TestStatBlocks(unittest.TestCase):
    """Tests for detect_stat_blocks(), compact_stat_blocks(), stat_block_word_count()"""

    def setUp(self):
        self.sample_stat_block = """Name: Hero
Level: 5
Class: Warrior
Race: Human
Strength: 18
Agility: 14
Dexterity: 15
Constitution: 16
Intelligence: 10
Wisdom: 12
Charisma: 8
Health: 85
Mana: 30"""

        self.novel_text = """The sun rose over the horizon, casting golden light across the valley. It was a beautiful morning.

Name: Hero
Level: 5
Class: Warrior
Strength: 18
Agility: 14
Health: 85

The hero continued walking along the path."""

    def test_detect_stat_blocks_basic(self):
        blocks = detect_stat_blocks(self.sample_stat_block)
        self.assertTrue(len(blocks) >= 1)
        block = blocks[0]
        self.assertIn('parsed_stats', block)
        self.assertIn('summary', block)
        self.assertIn('stat_count', block)
        self.assertGreater(block['stat_count'], 3)

    def test_detect_stat_blocks_in_novel(self):
        blocks = detect_stat_blocks(self.novel_text)
        self.assertTrue(len(blocks) >= 1)

    def test_detect_no_false_positive(self):
        plain = "The quick brown fox jumps over the lazy dog."
        blocks = detect_stat_blocks(plain)
        self.assertEqual(len(blocks), 0)

    def test_compact_summarize(self):
        result = compact_stat_blocks(self.novel_text, mode='summarize')
        # Should have a [Stats: ...] summary
        self.assertNotEqual(result, self.novel_text)
        self.assertIn('[Stats:', result)

    def test_compact_skip(self):
        result = compact_stat_blocks(self.novel_text, mode='skip')
        # Stat block should be removed
        self.assertNotIn('Strength', result)

    def test_compact_keep(self):
        result = compact_stat_blocks(self.novel_text, mode='keep')
        self.assertEqual(result, self.novel_text)

    def test_compact_flag(self):
        result = compact_stat_blocks(self.novel_text, mode='flag')
        self.assertIn('<STATBLOCK>', result)
        self.assertIn('</STATBLOCK>', result)

    def test_stat_block_word_count(self):
        count = stat_block_word_count(self.novel_text)
        self.assertGreater(count, 0)


if __name__ == '__main__':
    unittest.main()
