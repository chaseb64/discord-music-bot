import array
import math

class AudioSpectrumAnalyzer:
    """
    Real-time FFT audio spectrum analyzer for 16-bit 48kHz stereo PCM.
    Maps frequency bins to logarithmically-spaced visualizer bands with perceptual weighting.
    """
    def __init__(self, num_bands: int = 36, fft_size: int = 256):
        self.num_bands = num_bands
        self.fft_size = fft_size
        self.half_size = fft_size // 2

        # Precompute Hanning window to prevent spectral leakage
        self.window = [
            0.5 * (1.0 - math.cos(2.0 * math.pi * i / (fft_size - 1)))
            for i in range(fft_size)
        ]

        # Logarithmic frequency boundaries (from 35 Hz up to 16 kHz)
        min_freq = 35.0
        max_freq = 16000.0
        sample_rate = 48000.0
        freq_per_bin = sample_rate / fft_size

        log_min = math.log10(min_freq)
        log_max = math.log10(max_freq)
        edges = [
            math.pow(10, log_min + (log_max - log_min) * (i / num_bands))
            for i in range(num_bands + 1)
        ]

        self.band_bins = []
        for i in range(num_bands):
            b_start = max(1, int(edges[i] / freq_per_bin))
            b_end = max(b_start + 1, int(edges[i + 1] / freq_per_bin))
            b_end = min(b_end, self.half_size)
            self.band_bins.append((b_start, b_end))

        # Peak decay smoothing memory
        self.current_levels = [0.0] * num_bands

    def analyze(self, pcm_bytes: bytes) -> list[float]:
        """
        Analyzes a raw 16-bit 48kHz stereo PCM audio chunk and returns
        a list of normalized amplitudes (0.0 to 1.0) for each frequency band.
        """
        if not pcm_bytes or len(pcm_bytes) < self.fft_size * 4:
            # Gradually decay levels when no sound is present
            for i in range(self.num_bands):
                self.current_levels[i] = max(0.0, self.current_levels[i] * 0.85)
            return [round(x, 3) for x in self.current_levels]

        # Unpack signed 16-bit stereo PCM
        samples = array.array('h')
        samples.frombytes(pcm_bytes[:self.fft_size * 4])

        # Mix stereo to mono and apply Hanning window
        real = [
            (((samples[i * 2] + samples[i * 2 + 1]) / 65536.0) * self.window[i])
            for i in range(self.fft_size)
        ]
        imag = [0.0] * self.fft_size

        # In-place Cooley-Tukey Radix-2 FFT
        n = self.fft_size
        j = 0
        for i in range(n - 1):
            if i < j:
                real[i], real[j] = real[j], real[i]
                imag[i], imag[j] = imag[j], imag[i]
            k = n >> 1
            while k <= j:
                j -= k
                k >>= 1
            j += k

        step = 1
        while step < n:
            jump = step << 1
            angle_step = -math.pi / step
            for m in range(step):
                wr = math.cos(m * angle_step)
                wi = math.sin(m * angle_step)
                for i in range(m, n, jump):
                    pair = i + step
                    tr = wr * real[pair] - wi * imag[pair]
                    ti = wr * imag[pair] + wi * real[pair]
                    real[pair] = real[i] - tr
                    imag[pair] = imag[i] - ti
                    real[i] += tr
                    imag[i] += ti
            step = jump

        # Magnitude spectrum
        magnitudes = [
            math.sqrt(real[k] * real[k] + imag[k] * imag[k])
            for k in range(self.half_size)
        ]

        # Aggregate into visualizer bands with perceptual loudness curve
        new_levels = []
        for idx, (b_start, b_end) in enumerate(self.band_bins):
            if b_start >= self.half_size:
                new_levels.append(0.0)
                continue

            chunk = magnitudes[b_start:b_end]
            avg = sum(chunk) / len(chunk) if chunk else 0.0

            # Perceptual boost for high frequencies to balance the visualizer
            freq_boost = 1.0 + (idx / self.num_bands) * 2.5
            raw_amp = math.sqrt(avg * 4.5) * freq_boost
            val = min(1.0, max(0.0, raw_amp))

            # Fast attack (snap to peak), smooth decay (falloff)
            if val > self.current_levels[idx]:
                self.current_levels[idx] = val
            else:
                self.current_levels[idx] = self.current_levels[idx] * 0.78 + val * 0.22

            new_levels.append(round(self.current_levels[idx], 3))

        return new_levels
