import os
import sys
import unittest

# Ensure src directory is in sys.path
sys.path.insert(0, os.path.abspath('src'))

from utils.lyrics import clean_title


class TestCleanTitleEdgeCases(unittest.TestCase):

    def test_empty_and_falsy_inputs(self):
        self.assertEqual(clean_title(""), ("", ""))
        self.assertEqual(clean_title(None), ("", ""))
        self.assertEqual(clean_title("   "), ("", ""))

    def test_multiple_hyphens(self):
        title, artist = clean_title("Artist Name - Song Title - Live Version")
        self.assertEqual(artist, "Artist Name")
        self.assertEqual(title, "Song Title - Live Version")

    def test_case_insensitive_bracket_stripping(self):
        title, artist = clean_title("Artist - Song Title (OFFICIAL MUSIC VIDEO)")
        self.assertEqual(artist, "Artist")
        self.assertEqual(title, "Song Title")

        title2, artist2 = clean_title("Artist - Song Title [Official Audio]")
        self.assertEqual(artist2, "Artist")
        self.assertEqual(title2, "Song Title")

        title3, artist3 = clean_title("Artist - Song Title (LYRICS)")
        self.assertEqual(artist3, "Artist")
        self.assertEqual(title3, "Song Title")

    def test_featuring_and_producer_variations(self):
        title1, artist1 = clean_title("Artist - Song Title feat. Featured Artist")
        self.assertEqual(artist1, "Artist")
        self.assertEqual(title1, "Song Title")

        title2, artist2 = clean_title("Artist - Song Title ft. Featured Artist")
        self.assertEqual(artist2, "Artist")
        self.assertEqual(title2, "Song Title")

        title3, artist3 = clean_title("Artist - Song Title FEAT. Featured Artist")
        self.assertEqual(artist3, "Artist")
        self.assertEqual(title3, "Song Title")

        title4, artist4 = clean_title("Artist - Song Title (prod. Producer Name)")
        self.assertEqual(artist4, "Artist")
        self.assertEqual(title4, "Song Title")

    def test_multiple_brackets_and_whitespace_normalization(self):
        title, artist = clean_title("  Artist Name  -  Song   Title  [4K]  (Official Audio)  [Remastered]  ")
        self.assertEqual(artist, "Artist Name")
        self.assertEqual(title, "Song Title")

    def test_title_without_artist(self):
        title, artist = clean_title("Standalone Song Title (Official Video)")
        self.assertEqual(artist, "")
        self.assertEqual(title, "Standalone Song Title")


if __name__ == "__main__":
    unittest.main()
