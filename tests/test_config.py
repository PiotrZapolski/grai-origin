from origin import config


def test_every_threshold_has_a_source():
    """Global Constraint 7."""
    for name, threshold in config.THRESHOLDS.items():
        assert threshold.source in ("calibrated", "manual"), name


def test_thresholds_match_the_specification():
    assert config.THRESHOLDS["EXACT_PEAK_RATIO"].value == 0.60
    # VERSION_QMAX no longer carries the 0.55 starting value from section 9.2:
    # it was measured on real audio on 2026-08-26 and moved to 0.25 together
    # with the binarisation sieve it depends on (docs/calibration-harmonic.md).
    # A calibrated threshold that still equals its starting value is a
    # threshold nobody has measured.
    assert config.THRESHOLDS["VERSION_QMAX"].value == 0.25
    assert config.THRESHOLDS["VERSION_MAX_PEAK_RATIO"].value == 0.40
    assert config.THRESHOLDS["EXCERPT_MIN_REPETITIONS"].value == 2


def test_version_threshold_is_above_the_noise_floor():
    """Section 9.1: the 0.40 threshold closes the gap between 0.25 and 0.40."""
    assert (config.THRESHOLDS["VERSION_MAX_PEAK_RATIO"].value
            > config.THRESHOLDS["FINGERPRINT_NOISE_FLOOR"].value)


def test_cpu_quota_has_a_default_value():
    assert config.CPU_QUOTA >= 2
