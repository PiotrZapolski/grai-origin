"""The calibration model per evidentiary class. Section 10 of the specification."""
import numpy as np
import pytest

from origin import calibration as cal


@pytest.fixture
def data():
    rng = np.random.default_rng(0)
    X_pos = rng.normal(0.7, 0.1, (200, 7))
    X_neg = rng.normal(0.3, 0.1, (200, 7))
    X = np.vstack([X_pos, X_neg])
    y = np.array([1] * 200 + [0] * 200)
    return X, y


def test_the_model_returns_a_probability_in_range(data):
    X, y = data
    m = cal.fit(X, y, verdict_class="VERSION")
    p = m.predict_proba(X[0])
    assert 0.0 <= p <= 1.0


def test_a_separate_model_per_class(data):
    """Section 10.2: the probability for VERSION is a different quantity than for EXCERPT."""
    X, y = data
    a = cal.fit(X, y, verdict_class="VERSION")
    b = cal.fit(X, y[::-1], verdict_class="EXCERPT_PHONOGRAM")
    assert a.verdict_class != b.verdict_class
    assert not np.allclose(a.coefficients, b.coefficients)


def test_a_missing_feature_is_not_zero(data):
    """Section 10.2: zero is an informative value and it shifts the weights."""
    X, y = data
    m = cal.fit(X, y, verdict_class="VERSION")
    features = {"A.peak_ratio": 0.8, "B.qmax": 0.7, "B.coverage": 0.6,
                "C.longest_common_run": None, "D.jaccard": None,
                "D.semantic_sim": None, "mean_idf": 9.0}
    values, availability = cal.to_vector(features)
    assert availability[3] == 0.0, "the availability indicator says the feature was absent"
    assert len(values) == len(availability)


def test_the_regression_gives_weights_that_can_be_shown(data):
    """Section 10.2: a regression is chosen over a forest so that it can be explained."""
    X, y = data
    m = cal.fit(X, y, verdict_class="VERSION")
    assert len(m.coefficients) == 7
    assert m.feature_names


def test_the_metrics_contain_auc_ece_and_precision(data):
    X, y = data
    m = cal.fit(X[:300], y[:300], verdict_class="VERSION")
    met = cal.metrics(m, X[300:], y[300:])
    assert 0.0 <= met.auc <= 1.0
    assert met.ece >= 0.0
    assert met.reliability_curve


def test_the_operating_threshold_targets_a_precision_of_095(data):
    """Section 10.3: a false alarm about an infringement costs more than a miss."""
    X, y = data
    m = cal.fit(X[:300], y[:300], verdict_class="VERSION")
    threshold = cal.operating_threshold(m, X[300:], y[300:], target_precision=0.95)
    assert 0.0 < threshold < 1.0


def test_the_lyrics_class_has_no_model():
    """Section 10.4: the catalogue has no original-adaptation pairs."""
    assert cal.is_available("LYRICS") is False


def test_the_excerpt_work_class_has_no_model():
    assert cal.is_available("EXCERPT_WORK") is False


def test_a_missing_model_gives_the_status_uncalibrated():
    status = cal.probability_status("LYRICS")
    assert status == "uncalibrated"


def test_the_model_saves_and_loads(data, tmp_path):
    X, y = data
    m = cal.fit(X, y, verdict_class="VERSION")
    m.save(tmp_path / "v.joblib")
    loaded = cal.Model.load(tmp_path / "v.joblib")
    assert np.allclose(loaded.predict_proba(X[0]), m.predict_proba(X[0]))


# --- below: properties the brief does not check, which hold the heart of it ---


def test_a_missing_feature_enters_as_nan_not_as_a_number(data):
    """The vector carries NaN, so that inserting a zero cannot pass unnoticed."""
    features = dict.fromkeys(cal.FEATURE_NAMES, 0.5)
    features["D.jaccard"] = None
    values, availability = cal.to_vector(features)
    assert np.isnan(values[cal.FEATURE_NAMES.index("D.jaccard")])
    assert availability.tolist() == [1.0, 1.0, 1.0, 1.0, 0.0, 1.0, 1.0]


def test_a_missing_feature_gives_a_different_result_than_a_zero_in_that_feature(data):
    """If an absence were a zero, both calls would give the same. That is the whole argument."""
    X, y = data
    m = cal.fit(X, y, verdict_class="VERSION")
    features = dict.fromkeys(cal.FEATURE_NAMES, 0.7)
    features["B.qmax"] = None
    with_absence = m.predict_proba(cal.to_vector(features)[0])

    features_with_zero = dict.fromkeys(cal.FEATURE_NAMES, 0.7)
    features_with_zero["B.qmax"] = 0.0
    with_zero = m.predict_proba(cal.to_vector(features_with_zero)[0])

    assert not np.isclose(with_absence, with_zero)


def test_to_vector_rejects_an_unknown_feature():
    with pytest.raises(ValueError):
        cal.to_vector({"A.peak_ratio": 0.5, "B.invented": 0.5})


def test_the_design_vector_has_fourteen_dimensions(data):
    X, y = data
    m = cal.fit(X, y, verdict_class="VERSION")
    assert len(m.coefficients) == 7
    assert len(m.availability_coefficients) == 7


def test_predict_proba_accepts_a_feature_dictionary(data):
    X, y = data
    m = cal.fit(X, y, verdict_class="VERSION")
    features = dict.fromkeys(cal.FEATURE_NAMES, 0.7)
    assert 0.0 <= m.predict_proba(features) <= 1.0


def test_a_model_for_an_uncalibrated_class_is_not_created(data):
    """Section 10.4: LYRICS stays rule-based. The model cannot even be built."""
    X, y = data
    with pytest.raises(ValueError):
        cal.fit(X, y, verdict_class="LYRICS")


def test_lyrics_stays_uncalibrated_even_when_a_file_is_on_disk(tmp_path, monkeypatch):
    monkeypatch.setenv(cal.MODELS_DIR_ENV, str(tmp_path))
    (tmp_path / "calibration_LYRICS.joblib").write_bytes(b"whatever")
    (tmp_path / "calibration_EXCERPT_WORK.joblib").write_bytes(b"whatever")
    assert cal.is_available("LYRICS") is False
    assert cal.is_available("EXCERPT_WORK") is False
    assert cal.probability_status("LYRICS") == "uncalibrated"


def test_the_status_changes_only_once_a_model_lies_on_disk(data, tmp_path, monkeypatch):
    monkeypatch.setenv(cal.MODELS_DIR_ENV, str(tmp_path))
    assert cal.is_available("VERSION") is False
    assert cal.probability_status("VERSION") == "uncalibrated"

    X, y = data
    cal.fit(X, y, verdict_class="VERSION").save(cal.model_path("VERSION"))
    assert cal.is_available("VERSION") is True
    assert cal.probability_status("VERSION") == "calibrated"


def test_an_unknown_evidentiary_class_is_an_error():
    with pytest.raises(ValueError):
        cal.is_available("VERSJON")


def test_the_reliability_curve_adds_up_to_all_the_cases(data):
    X, y = data
    m = cal.fit(X[:300], y[:300], verdict_class="VERSION")
    met = cal.metrics(m, X, y)
    assert sum(b.count for b in met.reliability_curve) == len(y)
    assert met.auc_defined is True
    assert met.auc > 0.9


def test_auc_with_a_single_class_is_marked_as_undefined(data):
    """A test set without positives does not allow AUC to be computed. The metric has to admit that."""
    X, y = data
    m = cal.fit(X[:300], y[:300], verdict_class="VERSION")
    met = cal.metrics(m, X[300:], y[300:])
    assert met.auc_defined is False
    assert met.auc == 0.5


def test_the_operating_threshold_really_holds_the_required_precision(data):
    X, y = data
    training = np.r_[0:100, 200:300]
    test = np.r_[100:200, 300:400]
    m = cal.fit(X[training], y[training], verdict_class="VERSION")
    threshold = cal.operating_threshold(m, X[test], y[test], target_precision=0.95)
    alarms = m.predict_proba_batch(X[test]) >= threshold
    assert alarms.sum() > 0
    assert y[test][alarms].mean() >= 0.95


def test_training_on_a_single_class_is_an_error(data):
    X, y = data
    with pytest.raises(ValueError):
        cal.fit(X[:100], y[:100], verdict_class="VERSION")
