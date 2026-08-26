"""Checks that the remote environment stands at all."""
import sys


def test_python_version():
    assert sys.version_info >= (3, 11)


def test_numpy_works():
    import numpy as np

    assert np.array([1, 2, 3]).sum() == 6


def test_librosa_works():
    import librosa

    y = librosa.tone(440.0, sr=22050, length=22050)
    assert y.shape == (22050,)
