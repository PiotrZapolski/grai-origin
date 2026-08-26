"""Synthetic audio fixtures. Deterministic, no downloading, they work everywhere.

Real audio appears only in tests marked with @pytest.mark.integration.
"""
import numpy as np
import pytest
import soundfile as sf

SR = 22050

# One source of the progression for chord_wav and shifted_wav. Written twice it
# drifted apart after the first edit, and the promise "the same material" hung
# on a comment.
CHORDS = [
    [261.6, 329.6, 392.0],   # C
    [392.0, 493.9, 587.3],   # G
    [220.0, 261.6, 329.6],   # Am
    [349.2, 440.0, 523.3],   # F
]
SPEEDUP = 1.06


def _write(tmp_path, name: str, y: np.ndarray, sr: int = SR) -> str:
    path = tmp_path / name
    sf.write(path, y, sr)
    return str(path)


def tone(freq: float, dur: float, sr: int = SR) -> np.ndarray:
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    return 0.5 * np.sin(2 * np.pi * freq * t)


def chord(freqs: list[float], dur: float, sr: int = SR) -> np.ndarray:
    return sum(tone(f, dur, sr) for f in freqs) / len(freqs)


def progression(sr: int = SR) -> np.ndarray:
    """The C-G-Am-F progression, 2 s per chord."""
    return np.concatenate([chord(c, 2.0, sr) for c in CHORDS])


@pytest.fixture
def sine_wav(tmp_path) -> str:
    """A pure 440 Hz tone, 5 s."""
    return _write(tmp_path, "sine.wav", tone(440.0, 5.0))


@pytest.fixture
def chord_wav(tmp_path) -> str:
    """The C-G-Am-F progression, 2 s per chord. Material for detector B and the IDF filter."""
    return _write(tmp_path, "chord.wav", progression())


@pytest.fixture
def shifted_wav(tmp_path) -> str:
    """The same material as chord_wav, sped up by 6%. Material for the MODIFIED class.

    Resampling with a fixed step shortens the signal and raises the pitch at the
    same time, that is it gives a speedup rather than a pure time-stretch. That
    is the point of the MODIFIED class.
    """
    y = progression()
    idx = np.arange(0, len(y), SPEEDUP)
    y_faster = np.interp(idx, np.arange(len(y)), y)
    return _write(tmp_path, "shifted.wav", y_faster)


@pytest.fixture
def silence_wav(tmp_path) -> str:
    """Silence with a short tone in the middle. Material for silence trimming."""
    y = np.concatenate([np.zeros(SR * 2), tone(440.0, 1.0), np.zeros(SR * 2)])
    return _write(tmp_path, "silence.wav", y)


@pytest.fixture
def noise_wav(tmp_path) -> str:
    """White noise. A negative control - nothing should match against it."""
    rng = np.random.default_rng(42)
    return _write(tmp_path, "noise.wav", rng.normal(0, 0.1, SR * 5))


# --- shortlist candidates (task 10) -----------------------------------------
#
# Synthetic, without audio: the descriptor goes straight into the harmonic
# cache under an audio_path that is never read. shortlist.score reads it from
# there through harmonic.representation, exactly as for a real recording -
# thanks to that the ordering test has something to sort without a single audio
# file.


def _write_descriptor_to_cache(audio_path: str, descriptor) -> None:
    from origin import cache as _origin_cache
    from origin.detectors import harmonic as _harmonic

    _origin_cache.save_npz(
        _harmonic.cache_path(audio_path),
        {
            "chroma": np.zeros((12, 1), dtype=np.float32),
            "descriptor": descriptor.astype(np.float32),
            "chords": np.array([], dtype="<U8"),
        },
        compressed=True,
    )


def _fake_candidates(tmp_path, monkeypatch, count: int, seed: int):
    from origin.contracts import Candidate
    from origin.detectors import harmonic as _harmonic

    monkeypatch.setenv("ORIGIN_CACHE_DIR", str(tmp_path / "cache"))
    rng = np.random.default_rng(seed)
    candidates = []
    for i in range(count):
        audio_path = str(tmp_path / f"fake-{i}.wav")
        descriptor = rng.normal(size=_harmonic.DESCRIPTOR_DIM).astype(np.float32)
        _write_descriptor_to_cache(audio_path, descriptor)
        candidates.append(Candidate(
            id=f"fake-{i}",
            name=f"Fake {i}",
            artist="Fake Artist",
            source_url="https://example.com/fake",
            audio_path=audio_path,
        ))
    return candidates


@pytest.fixture
def fake_candidates_40(tmp_path, monkeypatch) -> list:
    """40 synthetic candidates with descriptors in the harmonic cache."""
    return _fake_candidates(tmp_path, monkeypatch, 40, seed=10)


@pytest.fixture
def fake_candidates_5(tmp_path, monkeypatch) -> list:
    """5 synthetic candidates with descriptors in the harmonic cache."""
    return _fake_candidates(tmp_path, monkeypatch, 5, seed=5)


# --- negative control for the confidence gate (task 14) ----------------------


@pytest.fixture
def instrumental_audio(tmp_path) -> str:
    """A recording without vocals. The negative control for the confidence gate of 7.3."""
    melody = np.concatenate([tone(f, 0.5) for f in (523.3, 587.3, 659.3, 698.5)] * 4)
    return _write(tmp_path, "instrumental.wav", melody)


# --- the end-to-end run (task 22) -------------------------------------------
#
# Candidates with REAL audio, only synthetic. A descriptor injected into the
# cache, as in fake_candidates, is not enough: the pipeline also runs the
# fingerprint detector, which reads its own level 0 artifact, and that cannot
# be faked without a file. Four entries cover the four states the run has to
# cope with: the same recording, a different recording of the same material,
# unrelated material, and a candidate with no file on disk.

# The progression repeated three times, that is 24 s. Rule 1 of section 9.1
# requires a matched segment longer than 15 s, so eight seconds would not allow
# a reupload to be recognised even with a fingerprint matched at every point.
PROGRESSION_REPEATS = 3


def long_progression(sr: int = SR, repeats: int = PROGRESSION_REPEATS,
                     chord_length: float = 2.0) -> np.ndarray:
    """The C-G-Am-F progression repeated several times. Level 1 material."""
    return np.concatenate(
        [chord(c, chord_length, sr) for c in CHORDS] * repeats
    )


def _test_candidate(identifier: str, audio_path: str, **fields):
    from origin.contracts import Candidate

    return Candidate(
        id=identifier,
        name=identifier,
        artist="Fixture",
        source_url=f"https://example.com/{identifier}",
        audio_path=audio_path,
        **fields,
    )


@pytest.fixture
def pipeline_query(tmp_path) -> str:
    """The query material: the C-G-Am-F progression three times over, 24 s."""
    return _write(tmp_path, "query.wav", long_progression())


@pytest.fixture
def pipeline_candidates(tmp_path, monkeypatch) -> list:
    """Four candidates with a warm level 0 cache.

    `same` is the same recording as pipeline_query, `cover` the same material
    played at a different tempo and with a different timbre, `noise` is the
    negative control, `missing` a candidate from the manifest whose file nobody
    downloaded. The cache and the corpus go to tmp_path, so that the run does
    not depend on what happens to lie on the machine.
    """
    from origin import pipeline as _pipeline

    monkeypatch.setenv("ORIGIN_CACHE_DIR", str(tmp_path / "cache"))
    # The corpus deliberately points at a place that does not exist: the
    # commonality filter without a corpus degrades nothing, so the class in the
    # test depends on the 9.1 tree rather than on whichever corpus happens to
    # lie on the test machine's disk.
    monkeypatch.setenv("ORIGIN_CORPUS", str(tmp_path / "no-corpus.json"))

    rng = np.random.default_rng(22)
    material = {
        "same": long_progression(),
        # A shorter chord and a sawtooth instead of a sine: the same
        # progression, a different recording. The fingerprint must not catch,
        # the chroma must stay similar.
        "cover": np.concatenate(
            [
                sum(
                    np.sign(tone(f, 1.8)) * 0.3 + tone(f, 1.8)
                    for f in c
                ) / len(c)
                for c in CHORDS
            ] * PROGRESSION_REPEATS
        ),
        "noise": rng.normal(0, 0.1, SR * 24),
    }
    candidates = [
        _test_candidate(name, _write(tmp_path, f"{name}.wav", y), published=date)
        for (name, y), date in zip(material.items(), ("1970-01-01", "1990-01-01", None))
    ]
    candidates.append(
        _test_candidate("missing", str(tmp_path / "no-such-file.wav"))
    )
    # Level 0 from section 4: representations are computed before the run, not inside it.
    _pipeline.prewarm(candidates)
    return candidates
