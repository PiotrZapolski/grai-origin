"""Decision thresholds and configuration. Section 9.2 of the specification."""
import os
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Threshold:
    """A decision threshold. The `source` field describes the TARGET source, not whether a model already exists.

    Until a calibration model exists, thresholds marked as calibrated carry
    starting values. Whether the model exists is decided by
    calibration.is_available(), not by this field. The UI has to tell those two
    apart visually (sections 9.2 and 10.5).
    """
    value: float
    source: Literal["calibrated", "manual"]


THRESHOLDS: dict[str, Threshold] = {
    "EXACT_PEAK_RATIO": Threshold(0.60, "calibrated"),
    "EXACT_MIN_SPAN_S": Threshold(15.0, "manual"),
    "MODIFIED_PEAK_RATIO": Threshold(0.50, "calibrated"),
    "EXCERPT_PEAK_RATIO": Threshold(0.40, "calibrated"),
    "EXCERPT_MIN_REPETITIONS": Threshold(2, "manual"),
    "VERSION_MAX_PEAK_RATIO": Threshold(0.40, "calibrated"),
    # Measured on real audio, 2026-08-26, 542 pairs - one real cover pair and
    # 541 pairs of unrelated works - with the binarisation sieve at its
    # calibrated 30th percentile. Full sweep in docs/calibration-harmonic.md.
    #
    # qmax: the cover scores 0.293, the 541 unrelated pairs have a median of
    # 0.072 and a maximum of 0.222. 0.25 sits in that gap, above the 99.8th
    # percentile of the unrelated pairs and below the cover.
    # coverage: the cover reaches 0.655 while only 2.0% of the unrelated pairs
    # pass 0.50, so the 0.50 from the specification survives the measurement
    # unchanged and keeps 0.55 of headroom under the cover.
    # Together (rule 4 of section 9.1 requires both): 0 of 541 unrelated pairs
    # pass, that is precision 1.00 on the measured set, with an upper bound of
    # 0.55% on the false-alarm rate at 95% confidence.
    #
    # The recall side of this pair of numbers rests on ONE real cover pair -
    # the corpus available on the server contains one performance per work, so
    # it yields no further positives. Read them as calibrated against false
    # alarms and provisional against misses.
    "VERSION_QMAX": Threshold(0.25, "calibrated"),
    "VERSION_COVERAGE": Threshold(0.50, "calibrated"),
    "EXCERPT_WORK_MIN_RUN": Threshold(8, "manual"),
    "LYRICS_MAX_QMAX": Threshold(0.40, "manual"),
    "LYRICS_JACCARD": Threshold(0.50, "manual"),
    "COMMON_IDF_PERCENTILE": Threshold(0.01, "calibrated"),
    "FINGERPRINT_NOISE_FLOOR": Threshold(0.25, "manual"),
    # Thresholds for the offset-difference histogram of the fingerprint
    # detector (section 7.1). The description of what each one does sits next
    # to the constant that reads it - here there is only the value, so that no
    # threshold ends up with two sources.
    "FINGERPRINT_BIN_S": Threshold(0.1, "manual"),
    "FINGERPRINT_ALIGN_TOLERANCE_S": Threshold(0.5, "manual"),
    "FINGERPRINT_MIN_HASHES": Threshold(10, "manual"),
    "FINGERPRINT_REPEAT_SHARE": Threshold(0.5, "manual"),
    # Three thresholds from the 9.1 decision tree that table 9.2 does not list:
    # rule 2 requires B.qmax > 0.50, rule 4 D.semantic_sim > 0.70, and rule 5
    # B.coverage < 0.40. A missing entry did not mean the threshold was absent -
    # it meant it lived in the fusion code, that is, in a second source.
    "MODIFIED_QMAX": Threshold(0.50, "manual"),
    "VERSION_SEMANTIC_SIM": Threshold(0.70, "manual"),
    "EXCERPT_WORK_MAX_COVERAGE": Threshold(0.40, "manual"),
}


def threshold(name: str) -> float:
    """The threshold value. A missing key is a configuration error, not a reason for a default.

    Section 9.2: every threshold must have a single source. A fallback value
    written on the reader's side turns the reader into a second source - one
    visible neither in this dictionary nor in the interface that describes
    where thresholds come from.
    """
    return float(THRESHOLDS[name].value)

CPU_QUOTA = int(os.environ.get("ORIGIN_CPU_QUOTA", "4"))


def worker_count() -> int:
    """How many threads we may occupy on this machine. sched_getaffinity, never bare cpu_count.

    The target server reports 32 logical processors, while the GRAI ORIGIN
    quota is four cores. cpu_count would return 32 and would degrade the
    production workload running on the same machine.
    """
    try:
        available = len(os.sched_getaffinity(0))
    except AttributeError:  # macOS has no sched_getaffinity
        available = os.cpu_count() or 1
    return max(1, min(CPU_QUOTA, available))
SR_HARMONIC = 22050
SR_SPEECH = 16000
WINDOW_S = 10.0
HOP_S = 5.0
TARGET_LUFS = -23.0
MAX_DURATION_S = 180.0
# Silence trimming threshold at the edges, in decibels below the peak (section 6 step 4).
TRIM_TOP_DB = 30
# A window shorter than this is rejected: at 22050 Hz one second is 22050
# samples, and below the fingerprint detector's n_fft the STFT returns all
# zeros and chroma divides by zero.
MIN_WINDOW_S = 1.0
# Hard limit on the downloaded file. 180 s at 320 kbps is 7.2 MB, so the margin
# is ninefold. It guards against the situation where download_ranges cannot be
# applied to a format and, instead of three minutes, a whole three-hour
# recording comes down, which after decoding takes two gigabytes of RAM.
MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024
SHORTLIST_SIZE = 20
