"""Per-class calibration of the evidentiary classes. Section 10 of the specification.

This is the component that turns a demo into a product. The output of a
similarity function is not a confidence: 0.87 from Qmax does not mean an 87%
chance that it is true. Without calibration every confidence number on the
screen is an ornament.

Three things hold this module together and none of them may be bypassed:

1. **A missing feature enters through an availability indicator, never through
   a zero.** A detector may return not_applicable, gated or failed - that does
   not mean it measured zero. Zero is an informative value and inserted
   artificially it shifts the weights. The feature vector therefore has 7
   values plus 7 indicators, 14 dimensions in total, and a missing value
   travels as NaN so that a quiet zero has no way through. The NaN is replaced
   by the training-set mean, which is a neutral value, while the whole signal
   about the absence is carried by the indicator and its own weight.

2. **A separate model per evidentiary class.** The probability that a match
   labelled VERSION really is a cover is a different quantity than for
   EXCERPT_PHONOGRAM.

3. **Logistic regression, not a random forest.** It gives weights that can be
   shown and explained, it is robust on a small sample, and it naturally
   returns a probability.

The classes LYRICS and EXCERPT_WORK do not have and will not have calibration
(section 10.4). is_available returns False for them unconditionally, regardless
of whether a model file lies on disk. Honesty is provided by the label, not by
removing the class from the product.
"""
from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np

from origin.contracts import VERDICT_CLASSES, ProbabilityStatus

__all__ = [
    "FEATURE_NAMES", "NEVER_CALIBRATED", "MODELS_DIR_ENV",
    "Model", "Metrics", "ReliabilityBin",
    "fit", "to_vector", "is_available", "probability_status",
    "operating_threshold", "metrics", "model_path", "models_dir",
]

# Input features from section 10.2. The order is part of the contract: the
# availability indicator at index i refers to the feature at index i, and a
# stored model keeps its weights in that order.
FEATURE_NAMES: list[str] = [
    "A.peak_ratio",
    "B.qmax",
    "B.coverage",
    "C.longest_common_run",
    "D.jaccard",
    "D.semantic_sim",
    "mean_idf",
]
N_FEATURES = len(FEATURE_NAMES)

# Section 10.4. The catalogue has no original-adaptation pairs (translations
# are separate works), and the longest_common_run threshold for EXCERPT/work is
# entered by hand. Neither class will get a model, and it is not a matter of it
# not existing yet.
NEVER_CALIBRATED = frozenset({"LYRICS", "EXCERPT_WORK"})

MODELS_DIR_ENV = "ORIGIN_MODELS_DIR"
DEFAULT_MODELS_DIR = "models"

# Section 10.3: for legal use we aim at precision >= 0.95, because a false
# alarm about an infringement costs more than a miss.
TARGET_PRECISION = 0.95

# The calibration curve over 10 bins (section 10.3).
ECE_BINS = 10

# The operating threshold has to be usable as "p >= threshold", so neither 0.0
# nor 1.0 is a valid result: the first alarms always, the second never.
_EPS = 1e-6


class ReliabilityBin(NamedTuple):
    """One bin of the calibration curve: what we promised and what came of it."""
    lower: float
    upper: float
    mean_predicted: float
    observed: float
    count: int


@dataclass(frozen=True)
class Metrics:
    """The metrics from section 10.3.

    auc_defined is a separate field, because AUC does not exist for a test set
    with a single class. In that case we return 0.5, the value of a random
    classifier, and say outright that it is not a measurement. A silent 0.5
    would be a number pretending to be a result. precision_at_threshold is None
    when not a single alarm is raised at that threshold - precision without
    alarms is not zero but an uncomputed quantity.
    """
    auc: float
    auc_defined: bool
    ece: float
    precision_at_threshold: float | None
    threshold: float
    reliability_curve: list[ReliabilityBin]
    n: int


@dataclass(frozen=True, eq=False)
class Model:
    """Logistic regression for one evidentiary class.

    It holds the weights alone rather than a scikit-learn object: the
    probability is computed with a single dot product, so loading a model does
    not require sklearn and the file does not depend on the version of the
    library that wrote it.
    """
    verdict_class: str
    feature_names: list[str]
    value_weights: np.ndarray
    availability_weights: np.ndarray
    intercept: float
    feature_means: np.ndarray
    n_train: int

    @property
    def coefficients(self) -> np.ndarray:
        """The feature weights - the part of the model shown in the UI (section 10.2)."""
        return self.value_weights

    @property
    def availability_coefficients(self) -> np.ndarray:
        """Weights of the availability indicators. They say what the absence of a feature alone costs."""
        return self.availability_weights

    def design_row(self, features: Any) -> np.ndarray:
        """One row of the 14-dimensional design matrix for the given features."""
        return self._design(features)[0]

    def predict_proba(self, features: Any) -> float:
        """The probability of the positive class for a single case.

        Accepts a feature dictionary, a vector of 7 values (NaN means missing)
        or a ready 14-dimensional vector.
        """
        row = self._design(features)
        if row.shape[0] != 1:
            raise ValueError(
                "predict_proba computes one case; for a matrix use predict_proba_batch"
            )
        return float(self._proba(row)[0])

    def predict_proba_batch(self, features: Any) -> np.ndarray:
        """Probabilities for a matrix of cases."""
        return self._proba(self._design(features))

    def save(self, path: str | Path) -> Path:
        import joblib

        file = Path(path)
        file.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "verdict_class": self.verdict_class,
                "feature_names": list(self.feature_names),
                "value_weights": np.asarray(self.value_weights, dtype=float),
                "availability_weights": np.asarray(self.availability_weights, dtype=float),
                "intercept": float(self.intercept),
                "feature_means": np.asarray(self.feature_means, dtype=float),
                "n_train": int(self.n_train),
            },
            file,
        )
        return file

    @classmethod
    def load(cls, path: str | Path) -> "Model":
        import joblib

        data = joblib.load(Path(path))
        return cls(
            verdict_class=data["verdict_class"],
            feature_names=list(data["feature_names"]),
            value_weights=np.asarray(data["value_weights"], dtype=float),
            availability_weights=np.asarray(data["availability_weights"], dtype=float),
            intercept=float(data["intercept"]),
            feature_means=np.asarray(data["feature_means"], dtype=float),
            n_train=int(data["n_train"]),
        )

    # --- internals ----------------------------------------------------------

    def _design(self, features: Any) -> np.ndarray:
        values, availability = _split(features)
        return _design_matrix(values, availability, self.feature_means)

    def _proba(self, design: np.ndarray) -> np.ndarray:
        weights = np.concatenate([self.value_weights, self.availability_weights])
        return _sigmoid(design @ weights + self.intercept)


# --- feature vector ---------------------------------------------------------


def to_vector(features: dict[str, float | None]) -> tuple[np.ndarray, np.ndarray]:
    """A feature dictionary into a value vector and an availability vector of the same length.

    A missing feature (key absent or None) gives NaN in the value vector and
    0.0 in the indicator. NaN rather than 0.0, because zero is a valid
    measurement and inserted in place of an absence it lies about what the
    detector saw.
    """
    unknown = sorted(set(features) - set(FEATURE_NAMES))
    if unknown:
        raise ValueError(f"unknown features: {unknown}; allowed: {FEATURE_NAMES}")

    values = np.full(N_FEATURES, np.nan, dtype=float)
    availability = np.zeros(N_FEATURES, dtype=float)
    for i, name in enumerate(FEATURE_NAMES):
        value = features.get(name)
        if value is None:
            continue
        value = float(value)
        if np.isnan(value):
            continue
        values[i] = value
        availability[i] = 1.0
    return values, availability


def _split(features: Any) -> tuple[np.ndarray, np.ndarray]:
    """Any input into (values, availability), both of shape (n, 7)."""
    if isinstance(features, dict):
        values, availability = to_vector(features)
        return values.reshape(1, -1), availability.reshape(1, -1)

    X = np.asarray(features, dtype=float)
    if X.ndim == 1:
        X = X.reshape(1, -1)
    if X.ndim != 2:
        raise ValueError(f"expected a vector or a matrix, got shape {X.shape}")

    if X.shape[1] == N_FEATURES:
        values = X
        availability = (~np.isnan(X)).astype(float)
    elif X.shape[1] == 2 * N_FEATURES:
        values = X[:, :N_FEATURES]
        availability = X[:, N_FEATURES:]
    else:
        raise ValueError(
            f"expected {N_FEATURES} features or {2 * N_FEATURES} columns (features + indicators), "
            f"got {X.shape[1]}"
        )
    return values, availability


def _feature_means(values: np.ndarray, availability: np.ndarray) -> np.ndarray:
    """Means over the available observations. A feature absent from the whole set gives 0.0.

    This single case is not a breach of the rule "an absence is not a zero":
    the indicator column is then constantly zero, so the feature contributes
    nothing to the model and any constant under the NaN gives the same result.
    """
    mask = availability > 0
    total = np.where(mask, np.nan_to_num(values, nan=0.0), 0.0).sum(axis=0)
    count = mask.sum(axis=0)
    return np.divide(total, count, out=np.zeros(N_FEATURES, dtype=float), where=count > 0)


def _design_matrix(
    values: np.ndarray, availability: np.ndarray, means: np.ndarray
) -> np.ndarray:
    """14 columns: 7 values with the gaps filled by the mean and 7 indicators.

    Where the indicator says "there was none", the value is overwritten by the
    mean without looking at what arrived in the vector. Otherwise the indicator
    and the value could tell two different stories about the same measurement.
    """
    mask = availability > 0
    filled = np.where(mask, np.nan_to_num(values, nan=0.0), means)
    return np.hstack([filled, mask.astype(float)])


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -60.0, 60.0)))


# --- training ---------------------------------------------------------------


def _check_class(verdict_class: str) -> str:
    if verdict_class not in VERDICT_CLASSES:
        raise ValueError(
            f"unknown evidentiary class {verdict_class!r}; allowed: {list(VERDICT_CLASSES)}"
        )
    return verdict_class


def fit(
    features: Any,
    labels: Sequence[int] | np.ndarray,
    verdict_class: str,
    C: float = 1.0,
    max_iter: int = 1000,
) -> Model:
    """Trains a logistic regression for one evidentiary class.

    features is (n, 7) values with NaN in the gaps, or a ready (n, 14). The
    split into a training and a test set is done by the caller - fit trains on
    what it was given, and metrics computes on what it will be given.
    """
    _check_class(verdict_class)
    if verdict_class in NEVER_CALIBRATED:
        raise ValueError(
            f"the class {verdict_class} stays rule-based and explicitly uncalibrated (section 10.4); "
            "a model for it is not created, rather than 'not created yet'"
        )

    from sklearn.linear_model import LogisticRegression

    values, availability = _split(features)
    y = np.asarray(labels).ravel()
    if len(y) != values.shape[0]:
        raise ValueError(f"{values.shape[0]} examples, {len(y)} labels")
    if len(np.unique(y)) < 2:
        raise ValueError("the training set has one class; the regression has nothing to tell apart")

    means = _feature_means(values, availability)
    design = _design_matrix(values, availability, means)
    clf = LogisticRegression(C=C, max_iter=max_iter).fit(design, y)
    weights = np.asarray(clf.coef_).ravel()

    return Model(
        verdict_class=verdict_class,
        feature_names=list(FEATURE_NAMES),
        value_weights=weights[:N_FEATURES],
        availability_weights=weights[N_FEATURES:],
        intercept=float(np.asarray(clf.intercept_).ravel()[0]),
        feature_means=means,
        n_train=int(len(y)),
    )


# --- model availability -----------------------------------------------------


def models_dir() -> Path:
    """The models directory. Read on every call, because tests move it at runtime."""
    return Path(os.environ.get(MODELS_DIR_ENV, DEFAULT_MODELS_DIR))


def model_path(verdict_class: str) -> Path:
    return models_dir() / f"calibration_{_check_class(verdict_class)}.joblib"


def is_available(verdict_class: str) -> bool:
    """Whether calibration exists for this class.

    For LYRICS and EXCERPT_WORK always False, even when a model file lies on
    disk (section 10.4). Such a file could end up there by mistake or through
    training on labels the catalogue does not have - and then the UI would show
    a confidence computed out of nothing.
    """
    _check_class(verdict_class)
    if verdict_class in NEVER_CALIBRATED:
        return False
    return model_path(verdict_class).exists()


def probability_status(verdict_class: str) -> ProbabilityStatus:
    """The label for the UI (section 10.5). Uncalibrated says so about itself outright."""
    return "calibrated" if is_available(verdict_class) else "uncalibrated"


# --- metrics and threshold --------------------------------------------------


def _probabilities(model: Model, X: Any) -> np.ndarray:
    return np.asarray(model.predict_proba_batch(X), dtype=float).ravel()


def reliability_curve(
    p: np.ndarray, y: np.ndarray, bins: int = ECE_BINS
) -> list[ReliabilityBin]:
    """The calibration curve: does "90% confidence" hit 9 cases out of 10.

    Returns non-empty bins only. A bin without observations has no measured
    frequency, and a zero written there would look like a measurement in the
    UI.
    """
    edges = np.linspace(0.0, 1.0, bins + 1)
    result: list[ReliabilityBin] = []
    for i in range(bins):
        lower, upper = edges[i], edges[i + 1]
        # The last bin is closed on the right, so that p == 1.0 has somewhere to fall.
        mask = (p >= lower) & (p < upper) if i < bins - 1 else (p >= lower) & (p <= upper)
        count = int(mask.sum())
        if count == 0:
            continue
        result.append(ReliabilityBin(
            lower=float(lower),
            upper=float(upper),
            mean_predicted=float(p[mask].mean()),
            observed=float(y[mask].mean()),
            count=count,
        ))
    return result


def expected_calibration_error(curve: Sequence[ReliabilityBin], n: int) -> float:
    """ECE: the weighted mean distance between the promise and reality."""
    if n <= 0:
        return 0.0
    return float(sum(b.count * abs(b.observed - b.mean_predicted) for b in curve) / n)


def operating_threshold(
    model: Model,
    X: Any,
    y: Sequence[int] | np.ndarray,
    target_precision: float = TARGET_PRECISION,
) -> float:
    """The lowest threshold reaching the required precision, that is the widest reach at it.

    Section 10.3: a false alarm about an infringement costs more than a miss,
    so precision is the goal and recall is what adapts to it. When the required
    precision cannot be reached on this set, we return the most conservative of
    the observed thresholds rather than the first one that comes along - and
    that still has to be read as "this model does not deliver that precision".
    """
    p = _probabilities(model, X)
    y = np.asarray(y).ravel()
    candidates = np.unique(p)
    for threshold in candidates:
        alarms = p >= threshold
        if not alarms.any():
            continue
        if float(y[alarms].mean()) >= target_precision:
            return _clamp(float(threshold))
    return _clamp(float(candidates.max())) if candidates.size else 0.5


def _clamp(threshold: float) -> float:
    return float(min(max(threshold, _EPS), 1.0 - _EPS))


def metrics(
    model: Model,
    X_test: Any,
    y_test: Sequence[int] | np.ndarray,
    threshold: float | None = None,
    target_precision: float = TARGET_PRECISION,
) -> Metrics:
    """AUC, ECE, precision at the threshold and the calibration curve (section 10.3).

    Without a given threshold, the threshold is chosen on the same set the
    metrics are computed on. That is convenient for a single-run report, but it
    inflates the precision - a production threshold is chosen on a validation
    set and passed in here explicitly.
    """
    p = _probabilities(model, X_test)
    y = np.asarray(y_test).ravel()
    if len(p) != len(y):
        raise ValueError(f"{len(p)} predictions, {len(y)} labels")

    classes = np.unique(y)
    if len(classes) >= 2:
        from sklearn.metrics import roc_auc_score

        auc = float(roc_auc_score(y, p))
        auc_defined = True
    else:
        auc, auc_defined = 0.5, False

    chosen_threshold = threshold if threshold is not None else operating_threshold(
        model, X_test, y, target_precision
    )
    alarms = p >= chosen_threshold
    precision = float(y[alarms].mean()) if alarms.any() else None

    curve = reliability_curve(p, y)
    return Metrics(
        auc=auc,
        auc_defined=auc_defined,
        ece=expected_calibration_error(curve, len(y)),
        precision_at_threshold=precision,
        threshold=float(chosen_threshold),
        reliability_curve=curve,
        n=int(len(y)),
    )
