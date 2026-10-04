import os
import sys
import unittest

# Ensure src directory is in sys.path
sys.path.insert(0, os.path.abspath('src'))

from utils.audio_analyzer import AudioSpectrumAnalyzer


class TestAudioSpectrumAnalyzer(unittest.TestCase):

    def setUp(self):
        self.analyzer = AudioSpectrumAnalyzer()

    def test_analyze_empty_input(self):
        """Test analyze with empty byte string input."""
        result = self.analyzer.analyze(b"")
        self.assertEqual(len(result), self.analyzer.num_bands)
        self.assertEqual(result, [0.0] * self.analyzer.num_bands)

    def test_analyze_small_input(self):
        """Test analyze with input shorter than required fft bytes."""
        req_bytes = self.analyzer.fft_size * 4  # 512 * 4 = 2048

        # Very small payload
        small_pcm = b"\x00\x01" * 10
        result = self.analyzer.analyze(small_pcm)
        self.assertEqual(len(result), self.analyzer.num_bands)
        self.assertEqual(result, [0.0] * self.analyzer.num_bands)

        # Payload just below required bytes
        just_under_pcm = b"\x00" * (req_bytes - 1)
        result_under = self.analyzer.analyze(just_under_pcm)
        self.assertEqual(len(result_under), self.analyzer.num_bands)
        self.assertEqual(result_under, [0.0] * self.analyzer.num_bands)

    def test_decay_behavior_on_empty_or_small_input(self):
        """Test that non-zero levels decay gradually when empty or small inputs are provided."""
        # Initialize current levels with active signal values
        self.analyzer.current_levels = [1.0] * self.analyzer.num_bands

        # First call with empty input: 1.0 * 0.75 = 0.75
        result1 = self.analyzer.analyze(b"")
        self.assertEqual(result1, [0.75] * self.analyzer.num_bands)

        # Second call with small input: 0.75 * 0.75 = 0.5625 -> rounded to 0.562
        result2 = self.analyzer.analyze(b"small_chunk")
        expected_level2 = round(0.75 * 0.75, 3)
        self.assertEqual(result2, [expected_level2] * self.analyzer.num_bands)

        # Repeated calls with empty input should eventually decay levels below threshold to 0.0
        for _ in range(20):
            result = self.analyzer.analyze(b"")
        self.assertEqual(result, [0.0] * self.analyzer.num_bands)

    def test_custom_bands_and_fft_size(self):
        """Test analyzer with custom band count and FFT size configuration."""
        custom_analyzer = AudioSpectrumAnalyzer(num_bands=12, fft_size=256)
        req_bytes = custom_analyzer.fft_size * 4  # 256 * 4 = 1024

        # Empty input
        res_empty = custom_analyzer.analyze(b"")
        self.assertEqual(len(res_empty), 12)
        self.assertEqual(res_empty, [0.0] * 12)

        # Small input (< 1024 bytes)
        res_small = custom_analyzer.analyze(b"\x00" * 500)
        self.assertEqual(len(res_small), 12)
        self.assertEqual(res_small, [0.0] * 12)

        # Confirm full requirement byte calculation
        self.assertEqual(req_bytes, 1024)

    def test_valid_full_pcm_input(self):
        """Test analyze with sufficient PCM bytes (silent and non-silent)."""
        req_bytes = self.analyzer.fft_size * 4

        # Full silent frame
        silent_pcm = b"\x00" * req_bytes
        res_silent = self.analyzer.analyze(silent_pcm)
        self.assertEqual(len(res_silent), self.analyzer.num_bands)
        for val in res_silent:
            self.assertGreaterEqual(val, 0.0)
            self.assertLessEqual(val, 1.0)

        # Full dummy PCM frame with audio signal (non-zero)
        active_pcm = (b"\x10\x20\x30\x40" * (req_bytes // 4))
        res_active = self.analyzer.analyze(active_pcm)
        self.assertEqual(len(res_active), self.analyzer.num_bands)
        for val in res_active:
            self.assertGreaterEqual(val, 0.0)
            self.assertLessEqual(val, 1.0)


if __name__ == '__main__':
    unittest.main()
