import array
import math

class AudioSpectrumAnalyzer:
    """
    High-dynamic-range FFT audio spectrum analyzer for 16-bit 48kHz stereo PCM.
    Calculates true dBFS frequency magnitudes mapped to logarithmically-spaced visualizer bands
    with perceptual equal-loudness compensation and transient-preserving attack/decay.
    """
    def __init__(self, num_bands: int = 36, fft_size: int = 512):
        self.num_bands = num_bands
        self.fft_size = fft_size
        self.half_size = fft_size // 2
        self.sample_rate = 48000.0
        self.norm_factor = fft_size / 4.0

        # Precompute Hanning window to eliminate spectral leakage
        self.window = [
            0.5 * (1.0 - math.cos(2.0 * math.pi * i / (fft_size - 1)))
            for i in range(fft_size)
        ]

        # Logarithmic frequency boundaries (from 40 Hz deep sub-bass to 16 kHz high treble)
        min_freq = 40.0
        max_freq = 16000.0
        log_min = math.log10(min_freq)
        log_max = math.log10(max_freq)

        self.band_params = []
        for i in range(num_bands):
            freq = math.pow(10, log_min + (log_max - log_min) * (i / (num_bands - 1)))
            f_prev = math.pow(10, log_min + (log_max - log_min) * (max(0, i - 0.5) / (num_bands - 1)))
            f_next = math.pow(10, log_min + (log_max - log_min) * (min(num_bands - 1, i + 0.5) / (num_bands - 1)))

            c_bin = (freq / self.sample_rate) * fft_size
            bw_bins = max(0.5, ((f_next - f_prev) / self.sample_rate) * fft_size)

            # Perceptual Fletcher-Munson / pink noise equal-loudness tilt (+14 dB across spectrum)
            # Low frequencies naturally carry far more energy; tilt ensures highs and mids dance with equal vitality
            tilt_db = (i / (num_bands - 1)) * 14.0

            self.band_params.append({
                'c_bin': c_bin,
                'bw_bins': bw_bins,
                'tilt_db': tilt_db,
                'freq': freq
            })

        # Dynamic range configuration in decibels (dBFS)
        # -50 dBFS floor captures ambient decay without hiss; +6 dBFS ceiling provides headroom to avoid flat ceiling clipping
        self.min_db = -50.0
        self.max_db = 6.0
        self.db_range = self.max_db - self.min_db

        # Gamma curve parameter to expand dynamic contrast (makes punchy hits pop while quiet dips drop)
        self.gamma = 1.25

        # Peak decay smoothing memory
        self.current_levels = [0.0] * num_bands

    def analyze(self, pcm_bytes: bytes) -> list[float]:
        """
        Analyzes a raw 16-bit 48kHz stereo PCM audio chunk and returns
        a list of normalized, dynamic amplitudes (0.0 to 1.0) for each frequency band.
        """
        req_bytes = self.fft_size * 4
        if not pcm_bytes or len(pcm_bytes) < req_bytes:
            # Gradually decay levels when no sound is present
            for i in range(self.num_bands):
                self.current_levels[i] = max(0.0, self.current_levels[i] * 0.75)
                if self.current_levels[i] < 0.005:
                    self.current_levels[i] = 0.0
            return [round(x, 3) for x in self.current_levels]

        # Take the most recent fft_size frames (10.6ms slice) for minimum latency
        samples = array.array('h')
        samples.frombytes(pcm_bytes[-req_bytes:])

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

        # Normalized magnitude spectrum (0 dBFS sine wave maps to magnitude 1.0)
        magnitudes = [
            math.sqrt(real[k] * real[k] + imag[k] * imag[k]) / self.norm_factor
            for k in range(self.half_size)
        ]

        # Aggregate into visualizer bands with logarithmic decibel conversion
        new_levels = []
        for idx, p in enumerate(self.band_params):
            c_bin = p['c_bin']
            bw = p['bw_bins']

            if c_bin < 1.0:
                # Sub-bass below bin 1 (taper smoothly to zero at DC, ignoring DC offset bin 0)
                mag = magnitudes[1] * c_bin
            elif bw < 1.5:
                # Fractional bin interpolation for low frequencies
                k0 = int(c_bin)
                k1 = min(self.half_size - 1, k0 + 1)
                frac = c_bin - k0
                m0 = magnitudes[k0] if 0 <= k0 < self.half_size else 0.0
                m1 = magnitudes[k1] if 0 <= k1 < self.half_size else 0.0
                mag = m0 * (1.0 - frac) + m1 * frac
            else:
                # Transients-preserving combination: 70% peak + 30% average across bin spread
                b_start = max(1, int(c_bin - bw * 0.5))
                b_end = min(self.half_size, int(math.ceil(c_bin + bw * 0.5)))
                chunk = magnitudes[b_start:b_end]
                mag = (max(chunk) * 0.7 + (sum(chunk) / len(chunk)) * 0.3) if chunk else 0.0

            # Convert to decibels relative to full scale (dBFS)
            raw_db = 20.0 * math.log10(max(1e-4, mag))
            eff_db = raw_db + p['tilt_db']

            # Map dBFS to [0.0, 1.0] dynamic range
            norm = (eff_db - self.min_db) / self.db_range
            norm = max(0.0, min(1.0, norm))

            # Dynamic contrast power curve to expand visual separation
            curved = math.pow(norm, self.gamma)

            # Instant attack on beats, smooth decay on release
            if curved > self.current_levels[idx]:
                self.current_levels[idx] = curved
            else:
                self.current_levels[idx] = self.current_levels[idx] * 0.70 + curved * 0.30

            new_levels.append(round(self.current_levels[idx], 3))

        return new_levels
