import os
import sys
import unittest
import asyncio

# Ensure src directory is in sys.path
sys.path.insert(0, os.path.abspath('src'))

from cogs.music import sanitize_query, MAX_QUEUE_SIZE, MAX_QUERY_LENGTH
from utils.lyrics import clean_title, parse_lrc


class TestInputSanitizationAndHardening(unittest.TestCase):

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
