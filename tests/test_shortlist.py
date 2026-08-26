from origin import shortlist


def test_never_returns_more_than_the_limit(fake_candidates_40):
    assert len(shortlist.select(None, fake_candidates_40, limit=20)) <= 20


def test_keeps_descending_similarity_order(fake_candidates_40):
    result = shortlist.select(None, fake_candidates_40, limit=10)
    scores = [shortlist.score(None, c) for c in result]
    assert scores == sorted(scores, reverse=True)


def test_a_set_smaller_than_the_limit_passes_whole(fake_candidates_5):
    assert len(shortlist.select(None, fake_candidates_5, limit=20)) == 5


def test_an_empty_set_does_not_blow_up():
    assert shortlist.select(None, [], limit=20) == []
