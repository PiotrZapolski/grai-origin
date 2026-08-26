"""The title-collision filter and drawing the calibration sample. Section 5.4 of the specification."""
import os
from pathlib import Path

import pytest

from scripts import sample_calibration as sc

# The SHS export lies outside the repository (Projects/dataset) and weighs
# 40 MB, so it does not travel to the test machine with the code. The
# integration test skips itself when the file is absent - otherwise the whole
# run would light up red everywhere except the one machine where that dump
# happens to lie.
EXPORT = os.environ.get("ORIGIN_SHS_EXPORT") or str(
    Path(__file__).resolve().parents[2] / "dataset" / "export_20260701.csv.zip"
)


@pytest.fixture
def groups():
    return [
        sc.Group("Bohemian Rhapsody", [("Queen", "en", False), ("Braids", "en", False)]),
        sc.Group("Crazy", [("Seal", "en", False), ("Patsy Cline", "en", False)]),
        sc.Group("Home", [("Depeche Mode", "en", False), ("Diana Ross", "en", False)]),
        sc.Group("Have I Told You Lately", [("Van Morrison", "en", False),
                                            ("Rod Stewart", "en", False)]),
        sc.Group("Summertime", [(f"W{i}", "en", False) for i in range(1485)]),
        sc.Group("Solo Track Only Once", [("Solo", "en", False)]),
        sc.Group("All Instrumental Suite Here", [("A", None, True), ("B", None, True)]),
    ]


def test_rejects_groups_larger_than_ten(groups):
    p = sc.pool_from_groups(groups)
    assert not any(g.work_title == "Summertime" for g in p)


def test_rejects_short_titles_because_that_is_where_collisions_live(groups):
    """Section 5.4 condition 2: Crazy is Seal and Patsy Cline, two different works."""
    p = sc.pool_from_groups(groups)
    titles = {g.work_title for g in p}
    assert "Crazy" not in titles
    assert "Home" not in titles


def test_lets_distinguishable_titles_through(groups):
    p = sc.pool_from_groups(groups)
    titles = {g.work_title for g in p}
    assert "Bohemian Rhapsody" in titles
    assert "Have I Told You Lately" in titles


def test_rejects_singletons(groups):
    p = sc.pool_from_groups(groups)
    assert not any(g.work_title == "Solo Track Only Once" for g in p)


def test_rejects_groups_without_two_vocal_performances(groups):
    p = sc.pool_from_groups(groups)
    assert not any(g.work_title == "All Instrumental Suite Here" for g in p)


def test_at_most_one_pair_per_group(groups):
    """Section 5.4 condition 3: without it half the set is one work."""
    sample = sc.sample_pairs(sc.pool_from_groups(groups), n_pos=2, n_neg=0, seed=1)
    titles = [p.work_title for p in sample.positives]
    assert len(titles) == len(set(titles))


def test_singletons_are_the_negative_pool(groups):
    """Section 5.4: a work with one performance has no cover by definition."""
    assert any(g.work_title == "Solo Track Only Once"
               for g in sc.negative_pool_from_groups(groups))


def test_tightening_to_four_words_is_available(groups):
    """Section 5.4 quality control: if more than 1 pair in 20 is wrong, we tighten."""
    p = sc.pool_from_groups(groups, min_words=4)
    assert all(len(g.work_title.split()) >= 4 for g in p)


def test_the_draw_is_reproducible(groups):
    p = sc.pool_from_groups(groups)
    a = sc.sample_pairs(p, n_pos=2, n_neg=0, seed=7)
    b = sc.sample_pairs(p, n_pos=2, n_neg=0, seed=7)
    assert [x.work_title for x in a.positives] == [x.work_title for x in b.positives]


def test_the_default_sample_size_is_500_pairs():
    assert sc.DEFAULT_POSITIVES == 250
    assert sc.DEFAULT_NEGATIVES == 250


# --- below: properties of the filter and the negatives the brief does not check --


def test_a_positive_pair_has_two_different_performances_in_one_language(groups):
    sample = sc.sample_pairs(sc.pool_from_groups(groups), n_pos=2, n_neg=0, seed=3)
    assert sample.positives
    for pair in sample.positives:
        assert pair.label == 1
        assert pair.left.performer != pair.right.performer
        assert pair.left.language == pair.right.language
        assert not pair.left.instrumental and not pair.right.instrumental


def test_a_negative_joins_two_different_works():
    """Section 5.4: a negative has to be hard, so the same performer, a different work."""
    groups = [
        sc.Group("Long Enough Title Number One", [("Performer A", "en", False)]),
        sc.Group("Long Enough Title Number Two", [("Performer A", "en", False)]),
        sc.Group("Long Enough Title Number Three", [("Performer B", "en", False)]),
        sc.Group("Long Enough Title Number Four", [("Performer C", "en", False)]),
    ]
    sample = sc.sample_pairs([], n_pos=0, n_neg=2, seed=5,
                             negatives=sc.negative_pool_from_groups(groups))
    assert len(sample.negatives) == 2
    for pair in sample.negatives:
        assert pair.label == 0
        assert pair.work_title != pair.other_work_title
    assert any(p.kind == "negative_same_performer" for p in sample.negatives)


def test_the_negatives_are_reproducible_too():
    groups = [
        sc.Group(f"Long Enough Title Number {i:03d}", [(f"Performer {i % 5}", "en", False)])
        for i in range(40)
    ]
    negatives = sc.negative_pool_from_groups(groups)
    a = sc.sample_pairs([], n_pos=0, n_neg=6, seed=11, negatives=negatives)
    b = sc.sample_pairs([], n_pos=0, n_neg=6, seed=11, negatives=negatives)
    assert [(p.work_title, p.other_work_title) for p in a.negatives] == \
           [(p.work_title, p.other_work_title) for p in b.negatives]


def test_it_reads_the_csv_from_a_zip_as_a_stream(tmp_path):
    """pool() has to work on a zip, because that is how the SHS export lies (section 5.1)."""
    import zipfile

    rows = [
        "performance_id,performance_title,performer,language,instrumental,youtube_url,work_title",
        "1,Bohemian Rhapsody,Queen,English,False,https://y/1,Bohemian Rhapsody",
        "2,Bohemian Rhapsody,Braids,English,False,https://y/2,Bohemian Rhapsody",
        "3,Crazy,Seal,English,False,https://y/3,Crazy",
        "4,Crazy,Patsy Cline,English,False,https://y/4,Crazy",
        "5,Solo,Solo,English,False,https://y/5,Solo Track Only Once",
    ]
    file = tmp_path / "export.csv.zip"
    with zipfile.ZipFile(file, "w") as zf:
        zf.writestr("export.csv", "\n".join(rows) + "\n")

    p = sc.pool(str(file))
    assert [g.work_title for g in p] == ["Bohemian Rhapsody"]
    assert p[0].performances[0].youtube_url == "https://y/1"

    all_groups = sc.read_groups(str(file))
    assert {g.work_title for g in sc.negative_pool_from_groups(all_groups)} == \
           {"Solo Track Only Once"}


def test_the_items_to_fetch_have_the_keys_fetch_audio_understands():
    group = sc.Group("Have I Told You Lately", [
        sc.Performance("Van Morrison", "English", False, "101", "https://y/101"),
        sc.Performance("Rod Stewart", "English", False, "102", "https://y/102"),
    ])
    sample = sc.sample_pairs([group], n_pos=1, n_neg=0, seed=2)
    items = sc.fetch_items(sample)
    assert len(items) == 2
    assert {item["id"] for item in items} == {"101", "102"}
    assert all(item["url"].startswith("https://y/") for item in items)


def test_the_cli_writes_the_pairs_and_an_empty_field_for_the_listening_check(tmp_path):
    """The whole command line run on a small stand-in catalogue."""
    import json
    import zipfile

    rows = [
        "performance_id,performance_title,performer,language,instrumental,youtube_url,work_title",
        "1,x,Queen,English,False,https://y/1,Long Enough Title Number One",
        "2,x,Braids,English,False,https://y/2,Long Enough Title Number One",
        "3,x,Alpha,English,False,https://y/3,Long Enough Title Number Two",
        "4,x,Beta,English,False,https://y/4,Long Enough Title Number Two",
        "5,x,Solo A,English,False,https://y/5,Single Title Number Alpha",
        "6,x,Solo A,English,False,https://y/6,Single Title Number Beta",
        "7,x,Solo B,English,False,https://y/7,Single Title Number Gamma",
        "8,x,Solo C,English,False,https://y/8,Single Title Number Delta",
    ]
    file = tmp_path / "export.csv.zip"
    with zipfile.ZipFile(file, "w") as zf:
        zf.writestr("export.csv", "\n".join(rows) + "\n")
    output = tmp_path / "pairs.json"

    code = sc.main(["--csv", str(file), "--out", str(output),
                    "--n-pos", "2", "--n-neg", "2", "--overshoot", "1.0"])

    assert code == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["target"] == {"positives": 2, "negatives": 2}
    assert data["drawn"] == {"positives": 2, "negatives": 2}
    assert data["pool_groups"] == 2
    assert data["negative_pool_groups"] == 4
    assert len(data["pairs"]) == 4
    assert {p["label"] for p in data["pairs"]} == {0, 1}
    assert all(p["left"]["url"] and p["right"]["url"] for p in data["pairs"])
    # The listening check is done by a human, and until they do it the field has to say so.
    assert data["manual_qa"] == {"listened_pairs": 0, "wrong_pairs": None, "report": None}


@pytest.mark.integration
@pytest.mark.skipif(
    not Path(EXPORT).exists(),
    reason=f"no SHS export at {EXPORT} - 40 MB does not travel to the test machine",
)
def test_the_real_export_gives_a_pool_of_about_69_thousand():
    """Measured on export_20260701: 69,208 groups after the filter."""
    p = sc.pool(EXPORT)
    assert 60_000 < len(p) < 80_000
