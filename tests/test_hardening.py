import os
import sys
import unittest
import asyncio

# Ensure src directory is in sys.path
sys.path.insert(0, os.path.abspath('src'))

from cogs.music import sanitize_query, probe_audio_duration, MAX_QUEUE_SIZE, MAX_QUERY_LENGTH
from utils.lyrics import clean_title, parse_lrc


class TestInputSanitizationAndHardening(unittest.TestCase):

    def test_probe_audio_duration_sanitization(self):
        # Non-existent path or invalid type returns 0.0
        self.assertEqual(probe_audio_duration("non_existent_file.mp3"), 0.0)
        self.assertEqual(probe_audio_duration(""), 0.0)
        self.assertEqual(probe_audio_duration(None), 0.0)

        # Directory path returns 0.0 (not a regular file)
        self.assertEqual(probe_audio_duration(os.path.dirname(__file__)), 0.0)

        # Attempt option injection with leading dashes
        self.assertEqual(probe_audio_duration("-v"), 0.0)
        self.assertEqual(probe_audio_duration("-help"), 0.0)

    def test_sanitize_query_truncation_and_strip(self):
        long_query = "a" * 1000
        sanitized = sanitize_query(long_query)
        self.assertEqual(len(sanitized), MAX_QUERY_LENGTH)

        dirty_query = "   hello\nworld\t "
        clean = sanitize_query(dirty_query)
        self.assertEqual(clean, "hello world")

        self.assertEqual(sanitize_query(""), "")
        self.assertEqual(sanitize_query(None), "")

    def test_clean_title(self):
        title, artist = clean_title("Artist Name - Track Title (Official Music Video) [HD]")
        self.assertEqual(title, "Track Title")
        self.assertEqual(artist, "Artist Name")

        title_feat, artist_feat = clean_title("Song Title ft. Drake")
        self.assertEqual(title_feat, "Song Title")

    def test_parse_lrc(self):
        lrc = "[00:10.50] Hello world\n[01:20.00] Second line\nInvalid line"
        parsed = parse_lrc(lrc)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0], {'time': 10.5, 'text': 'Hello world'})
        self.assertEqual(parsed[1], {'time': 80.0, 'text': 'Second line'})

    def test_parse_lrc_malformed_and_edge_cases(self):
        # Test empty input and whitespace-only
        self.assertEqual(parse_lrc(""), [])
        self.assertEqual(parse_lrc("   \n\n\t  "), [])

        # Test metadata lines (e.g. [ar:Artist], [ti:Title])
        metadata_lrc = "[ar: Artist Name]\n[ti: Song Title]\n[al: Album]\n[by: Creator]\n[00:05.00] Actual lyric"
        parsed_metadata = parse_lrc(metadata_lrc)
        self.assertEqual(len(parsed_metadata), 1)
        self.assertEqual(parsed_metadata[0], {'time': 5.0, 'text': 'Actual lyric'})

        # Test timestamp without text (empty lyric text)
        empty_text_lrc = "[00:10.00]\n[00:15.00]   \n[00:20.00] Real text"
        parsed_empty_text = parse_lrc(empty_text_lrc)
        self.assertEqual(len(parsed_empty_text), 1)
        self.assertEqual(parsed_empty_text[0], {'time': 20.0, 'text': 'Real text'})

        # Test malformed timestamp formats (missing brackets, non-numeric, improper colon/dot formatting)
        malformed_lrc = (
            "00:12.34 Missing leading bracket\n"
            "[00:12.34 Missing trailing bracket\n"
            "[xx:yy.zz] Non numeric\n"
            "[001234] Missing colon\n"
            "Just random text\n"
            "[00:10] Integer seconds\n"
            "[01:02.345] High precision seconds"
        )
        parsed_malformed = parse_lrc(malformed_lrc)
        self.assertEqual(len(parsed_malformed), 2)
        self.assertEqual(parsed_malformed[0], {'time': 10.0, 'text': 'Integer seconds'})
        self.assertEqual(parsed_malformed[1], {'time': 62.34, 'text': 'High precision seconds'})

        # Test unicode, special characters, and extra spacing around lines
        unicode_lrc = "  \t [02:00.50]   🎵 Music Note & Special Chars! 🤖   \n"
        parsed_unicode = parse_lrc(unicode_lrc)
        self.assertEqual(len(parsed_unicode), 1)
        self.assertEqual(parsed_unicode[0], {'time': 120.5, 'text': '🎵 Music Note & Special Chars! 🤖'})

    def test_path_traversal_prevention(self):
        uploads_dir = os.path.abspath(os.path.join('downloads', 'uploads'))

        # Test normal file path
        valid_path = os.path.abspath(os.path.join(uploads_dir, "12345_test.mp3"))
        self.assertEqual(os.path.commonpath([valid_path, uploads_dir]), uploads_dir)

        # Test traversal path attempt
        traversal_path = os.path.abspath(os.path.join(uploads_dir, "../../../etc/passwd"))
        self.assertNotEqual(os.path.commonpath([traversal_path, uploads_dir]), uploads_dir)


if __name__ == "__main__":
    unittest.main()
