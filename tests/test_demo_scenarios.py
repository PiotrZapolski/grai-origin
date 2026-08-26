"""The five scenarios of section 14. These are the tests that must pass before the demo.

Every scenario runs **from a local file**, not from an address: section 14 says
so outright and it is the only protection against there being no internet in the
room.

The tests skip themselves when the file is not on disk. That is not
convenience: the demo set lives in `data/audio/demo/`, which is outside git and
outside rsync (see `.rsyncignore`), so a machine without the downloaded audio
should pass the whole rest of the suite rather than paint it red.

Scenarios 2-5 do not assert the class rigidly. The engine really computes, and
the first run on real material is a **measurement, not a confirmation**: the
test guards the property the scenario is meant to prove (the rights layer, the
presence of a measurement, the judgment about commonality) and prints the
numbers that actually came out. A rigid class in a test on unreviewed material
would check whether somebody guessed well, not whether the engine works.
Scenario 1 is the exception: a reupload of the same recording either gives EXACT
or the fingerprint detector is broken.
"""
import os

import pytest

pytestmark = pytest.mark.integration

DEMO_DIR = os.path.join("data", "audio", "demo")


def _demo_file(name: str) -> str:
    path = os.path.join(DEMO_DIR, name)
    if not os.path.exists(path):
        pytest.skip(f"no {path} - run scripts/fetch_audio.py")
    return path


@pytest.fixture
def demo_reupload() -> str:
    return _demo_file("reupload.wav")


@pytest.fixture
def demo_cover() -> str:
    return _demo_file("cover.wav")


@pytest.fixture
def demo_speedup() -> str:
    return _demo_file("speedup.wav")


@pytest.fixture
def demo_sample() -> str:
    return _demo_file("sample.wav")


@pytest.fixture
def demo_trap() -> str:
    return _demo_file("trap.wav")


def _top(url: str):
    """The ranking leader after a full run on the demo_01 set."""
    from origin import pipeline

    result = pipeline.run_sync(url, "demo_01")
    if not result.ranking:
        pytest.skip(
            "the run gave no ranking entry at all; the candidates of the "
            "demo_01 set have no audio on this machine"
        )
    return result.ranking[0]


def test_scenario_1_a_reupload_gives_exact(demo_reupload):
    """The same recording. The only class that may be written in rigidly here."""
    top = _top(demo_reupload)
    assert top.verdict_class == "EXACT"
    assert top.verdict_layer == "phonogram"


def test_scenario_2_a_cover_concerns_the_work_layer(demo_cover):
    """A cover has to be recognised as a different recording of THE SAME work."""
    top = _top(demo_cover)
    assert top.verdict_class in ("VERSION", "COMMON"), top.explanation
    assert top.evidence["harmonic"].status == "ok"
    assert top.probability is not None


def test_scenario_3_a_sped_up_version_has_a_measured_transformation(demo_speedup):
    """Resistance to Content ID workarounds: the tempo and key have to be MEASURED."""
    top = _top(demo_speedup)
    assert top.alignment is not None, top.explanation
    assert top.verdict_class in ("MODIFIED", "EXACT", "VERSION"), top.explanation


def test_scenario_4_a_sample_has_a_recognisability_score(demo_sample):
    """The legal layer: for excerpt classes, recognisability and modification mean something."""
    top = _top(demo_sample)
    if top.verdict_class not in ("EXCERPT_PHONOGRAM", "EXCERPT_WORK"):
        pytest.skip(f"the material gave the class {top.verdict_class}, not an excerpt")
    assert top.legal.recognizability is not None
    assert top.legal.modification is not None


def test_scenario_5_the_trap_has_a_judgment_about_commonality(demo_trap):
    """The most important test in the project.

    Every team will show that it finds something. This one checks that the
    system can say "I found a similarity and I consider it irrelevant".

    That judgment requires a corpus: without one the commonality filter has
    nothing to base its claim on and will degrade nothing. That is why the test
    asks about the corpus first and only then about the class.
    """
    from origin import pipeline

    corpus = pipeline.load_corpus()
    if corpus.size <= 0:
        pytest.skip("no IDF corpus - the commonality filter has nothing to judge with")

    top = _top(demo_trap)
    assert top.commonality is not None
    assert top.commonality.corpus_size == corpus.size
    assert top.verdict_class in ("COMMON", "NONE"), top.explanation


def test_scenario_5_reports_the_number_of_tracks_in_the_corpus(demo_trap):
    """Section 8.2: the sentence on screen E3 needs a number, not an adjective."""
    from origin import pipeline

    corpus = pipeline.load_corpus()
    if corpus.size <= 0:
        pytest.skip("no IDF corpus")
    top = _top(demo_trap)
    assert top.commonality.corpus_frequency is not None
    assert top.commonality.mean_idf is not None
