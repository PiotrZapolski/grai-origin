import numpy as np
import pytest
from origin import ingest


# --- transcoding through ffmpeg (fallback for containers libsndfile does not support) --


def test_load_clip_decodes_through_ffmpeg_when_libsndfile_does_not_know_the_codec(tmp_path):
    """A path from a repair: libsndfile does not know AAC, so the whole corpus in
    m4a bounced off as "Format not recognised" after librosa 1.0 removed the
    fallback to audioread. _decode has to transcode through ffmpeg into a
    temporary WAV and read that file.
    """
    import os
    import shutil
    import subprocess

    import soundfile as sf

    ffmpeg = os.environ.get("ORIGIN_FFMPEG") or shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("no ffmpeg in PATH/ORIGIN_FFMPEG")

    sr = 22050
    dur = 5.0
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    y = 0.5 * np.sin(2 * np.pi * 440 * t)
    source = tmp_path / "src.wav"
    sf.write(source, y, sr)

    # AAC/m4a is exactly the case from the corpus; mp3 as a fallback container
    # in case this static ffmpeg was compiled without the aac encoder.
    encoded = None
    for name, codec in (("encoded.m4a", "aac"), ("encoded.mp3", "libmp3lame")):
        target = tmp_path / name
        result = subprocess.run(
            [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-i", str(source), "-c:a", codec, str(target)],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and target.exists():
            encoded = target
            break
    if encoded is None:
        pytest.skip("static ffmpeg without an aac or mp3 encoder")

    # A precondition of the test: libsndfile really does not open this
    # container, so below we are proving the transcoding path rather than
    # accidentally the primary path through soundfile.
    with pytest.raises(Exception):
        sf.read(str(encoded))

    clip = ingest.load_clip(str(encoded))
    assert clip.sr_harmonic == 22050
    assert clip.sr_speech == 16000
    assert clip.duration == pytest.approx(dur, abs=0.5)


def test_windows_have_50_percent_overlap(chord_wav):
    clip = ingest.load_clip(chord_wav)
    # the material is 8 s long, so the first window is closed at the end of the
    # material; the brief had (0.0, 10.0) here, and the coordinator resolved the
    # contradiction in favour of closing all windows - see split_into_windows.
    assert clip.windows[0] == (0.0, 8.0)
    assert clip.windows[1][0] == 5.0, "a hop of 5 s with a 10 s window"


def test_a_clip_shorter_than_the_window_gives_one_window(sine_wav):
    clip = ingest.load_clip(sine_wav)  # 5 s
    assert len(clip.windows) == 1
    assert clip.windows[0] == (0.0, 5.0)


def test_two_paths_with_different_sample_rates(chord_wav):
    clip = ingest.load_clip(chord_wav)
    assert clip.sr_harmonic == 22050
    assert clip.sr_speech == 16000
    assert len(clip.y_harmonic) > len(clip.y_speech)


def test_silence_at_the_edges_is_trimmed(silence_wav):
    clip = ingest.load_clip(silence_wav)
    assert clip.duration < 2.0, "a 5 s file, of which 4 s is silence at the edges"


def test_normalisation_levels_the_loudness(tmp_path):
    """Without this the energy thresholds are not comparable between sources."""
    import soundfile as sf
    t = np.linspace(0, 3, 22050 * 3, endpoint=False)
    quiet = 0.01 * np.sin(2 * np.pi * 440 * t)
    loud = 0.9 * np.sin(2 * np.pi * 440 * t)
    sf.write(tmp_path / "quiet.wav", quiet, 22050)
    sf.write(tmp_path / "loud.wav", loud, 22050)
    a = ingest.load_clip(str(tmp_path / "quiet.wav"))
    b = ingest.load_clip(str(tmp_path / "loud.wav"))
    assert abs(np.abs(a.y_harmonic).mean() - np.abs(b.y_harmonic).mean()) < 0.05


def test_sha_is_deterministic_and_differs_between_sources(chord_wav, noise_wav):
    assert ingest.load_clip(chord_wav).sha256 == ingest.load_clip(chord_wav).sha256
    assert ingest.load_clip(chord_wav).sha256 != ingest.load_clip(noise_wav).sha256


def test_long_material_is_trimmed_to_the_limit(tmp_path):
    import soundfile as sf
    t = np.linspace(0, 300, 22050 * 300, endpoint=False)
    sf.write(tmp_path / "long.wav", 0.5 * np.sin(2 * np.pi * 440 * t), 22050)
    clip = ingest.load_clip(str(tmp_path / "long.wav"))
    assert clip.duration <= 180.0


# --- source offset ----------------------------------------------------------


def _quiet_head(tmp_path, name="quiet_head.wav", sr=22050):
    """200 s of material: the first 100 s quiet, the rest at full scale."""
    import soundfile as sf
    t = np.linspace(0, 200, sr * 200, endpoint=False)
    y = np.sin(2 * np.pi * 440 * t)
    y[: sr * 100] *= 0.01
    sf.write(tmp_path / name, y, sr)
    return str(tmp_path / name)


def test_the_source_offset_points_at_the_real_place_in_the_recording(tmp_path):
    """Without the offset every query_span lies about the place in the source recording.

    Out of 200 s the highest-energy window is picked (starting at 20 s), and
    then silence is trimmed (another 80 s), so sample zero of the clip is second
    100 of the original. A/B playback without that number would land in a
    completely different place.
    """
    clip = ingest.load_clip(_quiet_head(tmp_path))
    assert clip.source_offset_s == pytest.approx(100.0, abs=0.2)
    assert clip.duration == pytest.approx(100.0, abs=0.2)


def test_the_source_offset_is_zero_when_nothing_was_cut(sine_wav):
    assert ingest.load_clip(sine_wav).source_offset_s == 0.0


def test_longer_material_is_cut_to_the_highest_energy_fragment(tmp_path):
    """A quiet start and a loud end: the end survives, not the first 180 s."""
    clip = ingest.load_clip(_quiet_head(tmp_path))
    assert clip.duration <= 180.0
    assert np.abs(clip.y_harmonic).mean() > 0.05


def test_from_array_goes_through_the_same_pipeline():
    """Candidates travel the same path as the query, section 6."""
    sr = 44100
    t = np.linspace(0, 5, sr * 5, endpoint=False)
    clip = ingest.Clip.from_array(0.5 * np.sin(2 * np.pi * 440 * t), sr)
    assert clip.sr_harmonic == 22050
    assert clip.sr_speech == 16000
    assert clip.windows == [(0.0, 5.0)]
    assert clip.source_offset_s == 0.0
    assert len(clip.sha256) == 64


# --- windowing --------------------------------------------------------------


def test_windows_are_closed_at_the_end_of_the_material():
    assert ingest.split_into_windows(12.0) == [(0.0, 10.0), (5.0, 12.0), (10.0, 12.0)]
    assert ingest.split_into_windows(8.0) == [(0.0, 8.0), (5.0, 8.0)]
    assert ingest.split_into_windows(3.0) == [(0.0, 3.0)]
    assert ingest.split_into_windows(0.0) == []


def test_the_last_window_must_not_be_a_stub():
    """0.05 s is 1102 samples, fewer than the fingerprint detector's n_fft - the STFT would give nan."""
    windows = ingest.split_into_windows(20.05)
    assert windows[-1] == (15.0, 20.05)
    assert all(end - start >= ingest.config.MIN_WINDOW_S for start, end in windows)


def test_the_only_window_survives_even_when_it_is_short():
    assert ingest.split_into_windows(0.4) == [(0.0, 0.4)]
