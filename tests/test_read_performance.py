import os
import sys
import time
import unittest
import discord

# Ensure src directory is in sys.path
sys.path.insert(0, os.path.abspath('src'))

from cogs.music import YTDLSource


class DummyPCMStream(discord.AudioSource):
    """Generates standard 3840-byte 16-bit 48kHz stereo PCM audio frames."""
    def __init__(self, frame_count=500):
        self.frame_count = frame_count
        self.current_frame = 0
        # Simulated PCM audio frame payload (3840 bytes)
        self.frame_data = b"\x10\x20\x30\x40" * 960

    def read(self) -> bytes:
        if self.current_frame < self.frame_count:
            self.current_frame += 1
            return self.frame_data
        return b""


class TestYTDLSourceReadPerformance(unittest.TestCase):

    def test_ytdlsource_read_performance(self):
        frame_count = 500
        dummy_stream = DummyPCMStream(frame_count=frame_count)
        player = YTDLSource(
            dummy_stream,
            data={'title': 'Benchmark Track', 'url': 'https://example.com'},
            file_path='test.mp3'
        )

        start_time = time.perf_counter()
        for _ in range(frame_count):
            data = player.read()
            self.assertEqual(len(data), 3840)
        total_duration = time.perf_counter() - start_time
        avg_per_read_ms = (total_duration / frame_count) * 1000.0

        print(f"\n[Benchmark YTDLSource.read] Total duration for {frame_count} frames: {total_duration:.4f}s ({avg_per_read_ms:.3f} ms/read)")

        # Verify EOF handling
        eof_data = player.read()
        self.assertEqual(eof_data, b"")
        self.assertEqual(player.latest_bands, [0.0] * 36)


if __name__ == '__main__':
    unittest.main()
