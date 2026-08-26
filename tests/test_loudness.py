"""BS.1770-4 loudness measurement. Tests moved here from test_ingest.py with the code.

Two anchors are absolute: the filter coefficients have to agree with the tables
of the standard, and a full-scale 1 kHz sine has to read -3.01 LKFS. Neither of
them measures itself against its own fixed point, so they survive a skewed
scale.
"""
import numpy as np
import pytest

from origin import ingest, loudness


# --- loudness measurement: absolute anchors ---------------------------------

# ITU-R BS.1770-4, tables 1 and 2. Coefficients for 48 kHz given verbatim in the standard.
STANDARD_SHELF_B = [1.53512485958697, -2.69169618940638, 1.19839281085285]
STANDARD_SHELF_A = [1.0, -1.69065929318241, 0.73248077421585]
STANDARD_RLB_B = [1.0, -2.0, 1.0]
STANDARD_RLB_A = [1.0, -1.99004745483398, 0.99007225036621]


def test_k_weighting_coefficients_match_the_tables_of_the_standard():
    """Absolute anchor number one: the filters have to be THOSE filters, not similar ones."""
    sos = loudness.k_weighting_sos(48000)
    assert np.allclose(sos[0][:3], STANDARD_SHELF_B, atol=1e-8), "table 1, numerator"
    assert np.allclose(sos[0][3:], STANDARD_SHELF_A, atol=1e-8), "table 1, denominator"
    assert np.allclose(sos[1][:3], STANDARD_RLB_B, atol=1e-8), "table 2, numerator"
    assert np.allclose(sos[1][3:], STANDARD_RLB_A, atol=1e-8), "table 2, denominator"


@pytest.mark.parametrize("sr", [48000, 22050, 16000])
def test_full_scale_1k_sine_reads_minus_3_01_lkfs(sr):
    """Absolute anchor number two: the standard gives this value outright.

    A 1 kHz sine with amplitude 1.0 has to read -3.01 LKFS. A bare power
    measurement would give -3.01 - 0.691 = -3.70, so this test checks that
    K-weighting contributes at 1 kHz exactly the +0.691 dB the standard assumes
    there. A test against its own fixed point (normalise, then measure with the
    same function) does not check that at all.
    """
    t = np.linspace(0, 3.0, int(sr * 3.0), endpoint=False)
    y = np.sin(2 * np.pi * 1000.0 * t).astype(np.float32)
    measured = loudness.measure_lufs(y, sr)
    assert measured == pytest.approx(-3.01, abs=0.1), f"sr={sr}, measured {measured:.4f}"


def test_normalisation_is_a_fixed_point_of_the_measurement(sine_wav):
    """Note: this is purely an internal consistency test, not a scale test.

    It measures the result with the same function that computed the gain, so it
    would pass for a skewed scale too. The scale is checked by the two tests
    above.
    """
    clip = ingest.load_clip(sine_wav)
    measured = loudness.measure_lufs(clip.y_harmonic, clip.sr_harmonic)
    assert abs(measured - ingest.config.TARGET_LUFS) < 0.5
