"""Checks that the audio fixtures from conftest really produce what they promise.

Without this, four subsequent tasks would discover a broken fixture only in
their own code.
"""
import numpy as np
import soundfile as sf

from tests.conftest import SPEEDUP

SR = 22050


def _peak_in_band(y: np.ndarray, sr: int, low: float, high: float) -> float:
    """The frequency of the strongest bin in the given band."""
    spectrum = np.abs(np.fft.rfft(y))
    frequencies = np.fft.rfftfreq(len(y), 1 / sr)
    mask = (frequencies >= low) & (frequencies <= high)
    return float(frequencies[mask][int(np.argmax(spectrum[mask]))])


def test_sine_wav_has_the_right_length_and_frequency(sine_wav):
    y, sr = sf.read(sine_wav)
    assert sr == SR
    assert len(y) == SR * 5
    assert abs(_peak_in_band(y, sr, 0.0, sr / 2) - 440.0) < 2.0


def test_chord_wav_lasts_eight_seconds(chord_wav):
    y, sr = sf.read(chord_wav)
    assert sr == SR
    assert len(y) == SR * 8


def test_chord_wav_starts_with_a_c_chord(chord_wav):
    y, sr = sf.read(chord_wav)
    assert abs(_peak_in_band(y[:int(1.8 * sr)], sr, 240.0, 300.0) - 261.6) < 2.0


def test_shifted_wav_is_sped_up_not_just_shorter(shifted_wav, chord_wav):
    """A speedup raises the pitch: C moves from 261.6 to 277.3 Hz."""
    y, sr = sf.read(shifted_wav)
    base_length = len(sf.read(chord_wav)[0])
    assert abs(len(y) - base_length / SPEEDUP) < 2
    expected = 261.6 * SPEEDUP
    assert abs(_peak_in_band(y[:int(1.8 * sr)], sr, 240.0, 300.0) - expected) < 2.0


def test_silence_wav_has_silence_at_the_edges(silence_wav):
    y, _ = sf.read(silence_wav)
    assert len(y) == SR * 5
    assert np.max(np.abs(y[:SR])) == 0.0
    assert np.max(np.abs(y[-SR:])) == 0.0
    assert np.max(np.abs(y[SR * 2:SR * 3])) > 0.1


def test_noise_wav_is_deterministic(noise_wav):
    y, sr = sf.read(noise_wav)
    assert sr == SR
    assert len(y) == SR * 5
    rng = np.random.default_rng(42)
    # A tolerance of 1e-4, because soundfile writes 16-bit PCM by default: the
    # quantisation step is 1/32768, that is about 3e-5. The fixture is
    # deterministic, but not bit for bit.
    assert np.allclose(y, rng.normal(0, 0.1, SR * 5), atol=1e-4)
