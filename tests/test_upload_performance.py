import asyncio
import os
import time
import tempfile
import unittest

class TestUploadPerformance(unittest.TestCase):
    def test_upload_chunk_writing_performance(self):
        async def write_blocking(dest, chunks):
            with open(dest, 'wb') as f:
                for chunk in chunks:
                    f.write(chunk)

        async def write_nonblocking(dest, chunks):
            with open(dest, 'wb') as f:
                for chunk in chunks:
                    await asyncio.to_thread(f.write, chunk)

        async def run_test(write_func):
            chunk_size = 1024 * 1024  # 1 MB chunk
            num_chunks = 30           # 30 MB total file size
            chunks = [os.urandom(chunk_size) for _ in range(num_chunks)]

            with tempfile.TemporaryDirectory() as tmpdir:
                dest = os.path.join(tmpdir, "test_upload.tmp")

                max_event_loop_delay = 0.0
                monitoring = True

                async def monitor_event_loop():
                    nonlocal max_event_loop_delay, monitoring
                    last_time = time.perf_counter()
                    while monitoring:
                        await asyncio.sleep(0.001)
                        now = time.perf_counter()
                        delay = (now - last_time) - 0.001
                        if delay > max_event_loop_delay:
                            max_event_loop_delay = delay
                        last_time = now

                monitor_task = asyncio.create_task(monitor_event_loop())

                start_time = time.perf_counter()
                await write_func(dest, chunks)
                duration = time.perf_counter() - start_time

                monitoring = False
                await monitor_task

                self.assertTrue(os.path.exists(dest))
                self.assertEqual(os.path.getsize(dest), num_chunks * chunk_size)

                return duration, max_event_loop_delay

        async def compare():
            blocking_dur, blocking_delay = await run_test(write_blocking)
            nonblocking_dur, nonblocking_delay = await run_test(write_nonblocking)

            print(f"\n[Benchmark] Blocking write: duration={blocking_dur:.4f}s, max_loop_delay={blocking_delay*1000:.2f}ms")
            print(f"[Benchmark] Non-blocking write: duration={nonblocking_dur:.4f}s, max_loop_delay={nonblocking_delay*1000:.2f}ms")

        asyncio.run(compare())

if __name__ == "__main__":
    unittest.main()
