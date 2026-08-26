"""Loudness measurement per ITU-R BS.1770-4 and gain to target. Step 3 of section 6.

A self-contained piece anchored in the standard, not in anybody's intuition:
the K-weighting filters must come out digit for digit as in tables 1 and 2 of
the standard, and a full-scale 1 kHz sine must read -3.01 LKFS. Both facts are
guarded by tests, and no constant in this module may be "rounded".

A real loudness measurement, not a peak and not an RMS, is the precondition for
energy thresholds in the detectors meaning the same thing for a vinyl rip and
for a studio master.
"""
from __future__ import annotations

import numpy as np
from scipy import signal

from origin import config

__all__ = [
    "k_weighting_sos",
    "measure_lufs",
    "gain_to_target",
]

# BS.1770-4: a 400 ms measurement block with 75 percent overlap and an absolute gate.
_BLOCK_S = 0.400
_OVERLAP = 0.75
_ABSOLUTE_GATE_LUFS = -70.0
_BS1770_OFFSET = -0.691

# Analogue prototype parameters from De Man's paper on BS.1770 implementations.
# Chosen so that at 48 kHz the biquads come out digit for digit as in tables 1
# and 2 of the standard, while for any other sample rate the filter is
# recomputed rather than hard-coded. The coefficient test guards that equality.
_SHELF_G = 3.999843853973347
_SHELF_Q = 0.7071752369554196
_SHELF_FC = 1681.974450955533
_RLB_Q = 0.5003270373238773
_RLB_FC = 38.13547087602444
# Gain exponent of the shelf transition band. This is not a rounded 0.5: only
# this value reproduces the numerator from table 1 of the standard.
_SHELF_VB_EXP = 0.4996667741545416


def k_weighting_sos(sr: int) -> np.ndarray:
    """The two K-weighting biquads per ITU-R BS.1770-4 as an SOS matrix (2, 6).

    Bilinear transform with prewarping through K = tan(pi * fc / sr). The RBJ
    cookbook formulas (alpha = sin(w0) / 2Q) give different poles here - at
    48 kHz the shelf denominator comes out as [1, -1.6538, 0.7054] instead of
    the standard's [1, -1.69066, 0.73248], which shifts the reading by about
    0.25 dB.
    """
    K = np.tan(np.pi * _SHELF_FC / sr)
    Vh = 10.0 ** (_SHELF_G / 20.0)
    Vb = Vh ** _SHELF_VB_EXP
    a0 = 1.0 + K / _SHELF_Q + K * K
    shelf = [
        (Vh + Vb * K / _SHELF_Q + K * K) / a0,
        2.0 * (K * K - Vh) / a0,
        (Vh - Vb * K / _SHELF_Q + K * K) / a0,
        1.0,
        2.0 * (K * K - 1.0) / a0,
        (1.0 - K / _SHELF_Q + K * K) / a0,
    ]

    K = np.tan(np.pi * _RLB_FC / sr)
    a0 = 1.0 + K / _RLB_Q + K * K
    # The numerator [1, -2, 1] is taken literally from table 2 of the standard,
    # without dividing by a0. This filter has a passband gain of 1.004995, not
    # 1.0, and that is not a bug to fix - those 0.043 dB are part of the
    # definition of the LKFS scale.
    rlb = [
        1.0,
        -2.0,
        1.0,
        1.0,
        2.0 * (K * K - 1.0) / a0,
        (1.0 - K / _RLB_Q + K * K) / a0,
    ]
    return np.array([shelf, rlb], dtype=np.float64)


def _k_weighting(y: np.ndarray, sr: int) -> np.ndarray:
    return signal.sosfilt(k_weighting_sos(sr), y.astype(np.float64))


def measure_lufs(y: np.ndarray, sr: int) -> float | None:
    """Integrated loudness in LUFS per BS.1770-4, with an absolute and a relative gate.

    Gating matters here: without it, silence at the edges of a recording would
    drag the measurement down and material with long silence would come out too
    loud after normalisation. Returns None when the material cannot be measured
    (too short, or silence).
    """
    block_length = int(round(_BLOCK_S * sr))
    hop = max(1, int(round(block_length * (1.0 - _OVERLAP))))
    if y.size < block_length:
        return None

    filtered = _k_weighting(y, sr)
    cumulative = np.concatenate(([0.0], np.cumsum(np.square(filtered))))
    starts = np.arange(0, filtered.size - block_length + 1, hop)
    z = (cumulative[starts + block_length] - cumulative[starts]) / block_length

    l = np.full(z.shape, -np.inf)
    nonzero = z > 0
    l[nonzero] = _BS1770_OFFSET + 10.0 * np.log10(z[nonzero])

    gate_a = l > _ABSOLUTE_GATE_LUFS
    if not gate_a.any():
        return None
    relative_gate = _BS1770_OFFSET + 10.0 * np.log10(z[gate_a].mean()) - 10.0
    gate_b = gate_a & (l > relative_gate)
    selected = z[gate_b] if gate_b.any() else z[gate_a]
    return float(_BS1770_OFFSET + 10.0 * np.log10(selected.mean()))


def gain_to_target(y: np.ndarray, sr: int) -> float:
    """The multiplier that brings the material to config.TARGET_LUFS.

    A real loudness measurement, not a peak and not an RMS: without it, an
    energy threshold would mean one thing for a vinyl rip and another for a
    studio master, and every detector threshold would start lying.
    """
    loudness = measure_lufs(y, sr)
    if loudness is None or not np.isfinite(loudness):
        return 1.0
    return float(10.0 ** ((config.TARGET_LUFS - loudness) / 20.0))
