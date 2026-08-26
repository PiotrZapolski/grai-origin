import json

import pytest

from origin import candidates


def test_loads_the_demo_set():
    candidate_set = candidates.load_set("demo_01")
    assert len(candidate_set.candidates) >= 8
    assert candidate_set.set_id == "demo_01"


def test_identifiers_are_unique():
    candidate_set = candidates.load_set("demo_01")
    ids = [c.id for c in candidate_set.candidates]
    assert len(ids) == len(set(ids))


def test_validator_rejects_published_source_youtube(tmp_path):
    """Global Constraint 8."""
    bad = {"set_id": "x", "candidates": [{
        "id": "c1", "name": "N", "artist": "A",
        "source_url": "https://youtube.com/watch?v=q",
        "audio_path": "data/audio/c1.wav",
        "published": "2020-01-01", "published_source": "youtube",
        "license": "unknown", "instrumental": False}]}
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad))
    errors = candidates.validate_set(str(p))
    assert any("youtube" in e for e in errors)


def test_validator_requires_a_date_source_when_a_date_is_given(tmp_path):
    bad = {"set_id": "x", "candidates": [{
        "id": "c1", "name": "N", "artist": "A",
        "source_url": "https://example.com/a",
        "audio_path": "data/audio/c1.wav",
        "published": "2020-01-01", "published_source": None,
        "license": "unknown", "instrumental": False}]}
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad))
    assert candidates.validate_set(str(p))


def test_the_demo_set_passes_validation():
    assert candidates.validate_set("data/candidates/demo_01.json") == []


def test_the_demo_set_has_an_instrumental_candidate():
    """Section 7.3: needed to check the routing of detector D."""
    candidate_set = candidates.load_set("demo_01")
    assert any(c.instrumental for c in candidate_set.candidates)


def test_the_demo_set_has_a_candidate_under_an_open_licence():
    """Scenario 6 from section 14."""
    candidate_set = candidates.load_set("demo_01")
    assert any(c.license.startswith("cc") for c in candidate_set.candidates)


# --- extra rules following from sections 5.5 and 9.3 ---


def _manifest(tmp_path, **overrides) -> str:
    candidate = {
        "id": "c1", "name": "N", "artist": "A",
        "source_url": "https://example.com/a",
        "audio_path": "data/audio/c1.wav",
        "published": None, "published_source": None,
        "license": "unknown", "instrumental": False,
    }
    candidate.update(overrides)
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"set_id": "x", "candidates": [candidate]}))
    return str(p)


def test_validator_accepts_a_missing_date(tmp_path):
    """Section 5.5: a missing date is valid, an invented date is a defect."""
    assert candidates.validate_set(_manifest(tmp_path)) == []


def test_validator_rejects_a_date_source_without_a_date(tmp_path):
    errors = candidates.validate_set(_manifest(tmp_path, published_source="manual"))
    assert any("published_source" in e for e in errors)


def test_validator_rejects_a_date_in_the_wrong_format(tmp_path):
    """The chronology rule from 9.3 parses this value, so it has to be ISO."""
    errors = candidates.validate_set(
        _manifest(tmp_path, published="1975", published_source="manual")
    )
    assert any("1975" in e for e in errors)


def test_validator_detects_duplicated_identifiers(tmp_path):
    candidate = {
        "id": "c1", "name": "N", "artist": "A",
        "source_url": "https://example.com/a",
        "audio_path": "data/audio/c1.wav",
        "published": None, "published_source": None,
        "license": "unknown", "instrumental": False,
    }
    p = tmp_path / "dup.json"
    p.write_text(json.dumps({"set_id": "x", "candidates": [candidate, dict(candidate)]}))
    errors = candidates.validate_set(str(p))
    assert any("c1" in e for e in errors)


def test_validator_reports_a_missing_file(tmp_path):
    errors = candidates.validate_set(str(tmp_path / "no-such-file.json"))
    assert len(errors) == 1


def test_load_set_reports_a_missing_set():
    with pytest.raises(FileNotFoundError):
        candidates.load_set("no_such_set")


def test_the_demo_set_has_no_dates_from_youtube():
    """Section 5.5: every date in the manifest is entered by hand."""
    candidate_set = candidates.load_set("demo_01")
    for c in candidate_set.candidates:
        if c.published is not None:
            assert c.published_source == "manual"


def test_the_demo_set_has_shs_identifiers():
    """Every candidate comes from the catalogue, so it can be found in the dump."""
    candidate_set = candidates.load_set("demo_01")
    assert all(c.shs_performance_id for c in candidate_set.candidates)


def test_the_demo_set_fits_the_limit_from_5_3():
    candidate_set = candidates.load_set("demo_01")
    assert 8 <= len(candidate_set.candidates) <= 12


def test_the_demo_set_has_a_spare_instrumental_candidate():
    """The list is by name, so there is no overshoot from 5.7 - the spare has to be explicit.

    A single instrumental candidate would mean that one dead address takes the
    whole routing test of detector D away with it.
    """
    candidate_set = candidates.load_set("demo_01")
    assert len([c for c in candidate_set.candidates if c.instrumental]) >= 2


def test_the_demo_set_has_a_spare_candidate_under_an_open_licence():
    """The same for scenario 6: one address must not be the only route."""
    candidate_set = candidates.load_set("demo_01")
    open_licensed = [c for c in candidate_set.candidates if c.license.startswith("cc")]
    assert len(open_licensed) >= 2
    # Different licence variants, so that the attribution generator cannot
    # hard-code a single string.
    assert len({c.license for c in open_licensed}) >= 2
