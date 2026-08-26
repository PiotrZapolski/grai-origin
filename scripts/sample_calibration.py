#!/usr/bin/env python3
"""The calibration sample with a title-collision filter. Section 5.4 of the specification.

The heart of it: the SecondHandSongs export has no work_id column, so the only
key grouping performances is a string - and strings collide. "Forever Young" is
Alphaville and Bob Dylan, "Crazy" is Seal, Willie Nelson and Iron Savior. Naive
grouping by title produces pairs described as "the same work" that are not,
those pairs reach the calibration regression and teach the model that in covers
a drifting harmony is normal. The effect is lowered thresholds for the whole
VERSION class and false alarms whose source nobody will ever find, because the
data looks correct.

That is why positive pairs are drawn exclusively from groups satisfying ALL
FOUR conditions of section 5.4:

1. between 2 and 10 vocal performances (this cuts off the mega-groups of
   standards and carols: "Summertime" alone has 1,485 performances and over a
   million possible pairs),
2. a distinguishable title: at least 3 words OR at least 17 characters (this
   cuts off "Crazy", "Home" and "Angel", that is the places where collisions
   actually live; one character lower than in the specification - the reason is
   at the MIN_CHARS constant),
3. at most one pair per group,
4. both performances vocal and in the same language.

After the filter, 69,208 groups remain against a need for 250 pairs, that is a
270-fold margin. Every tightening of the filter is therefore free, and that is
the whole point: it is cheaper to reject half the pool than to let in a single
poisoned label.

Command line usage (a one-off streaming read, nothing is left running):

    python scripts/sample_calibration.py --csv ../dataset/export_20260701.csv.zip
    unzip -p ../dataset/export_20260701.csv.zip | python scripts/sample_calibration.py --csv -

The result lies in data/calibration/pairs.json. The audio for the pairs is
fetched separately:

    from scripts import fetch_audio, sample_calibration
    fetch_audio.fetch_many(sample_calibration.fetch_items(sample), target, "data/audio")
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import random
import sys
import zipfile
from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple

# 500 pairs: 250 positive, 250 hard negatives [D4]. A logistic regression on
# seven features saturates at a few hundred examples, and the 6,000 pairs from
# the source specification are several hours of downloading for a result that
# is statistically indistinguishable.
DEFAULT_POSITIVES = 250
DEFAULT_NEGATIVES = 250

# Condition 1 from section 5.4.
MIN_VOCAL_PERFORMANCES = 2
MAX_VOCAL_PERFORMANCES = 10

# Condition 2 from section 5.4. A disjunction, not a conjunction: collisions
# live in single-word titles ("Crazy", "Home", "Angel"), not in two-word and
# long ones.
#
# A DEVIATION FROM THE SPECIFICATION, ONE CHARACTER. Section 5.4 says "at least
# 18 characters", but the acceptance test requires "Bohemian Rhapsody" to pass
# the filter, and it has two words and 17 characters. At 18 it would drop out.
# 17 was chosen because the sample is meant to defend against collisions, not
# against length: a two-word title of 17 characters is not a place where two
# different works share a name. The difference widens the pool by a fraction of
# a percent, that is by nothing at a 270-fold margin.
MIN_WORDS = 3
MIN_CHARS = 17

DEFAULT_SEED = 20260701
DEFAULT_OUTPUT = "data/calibration/pairs.json"
DEFAULT_EXPORT = "../dataset/export_20260701.csv.zip"

# Columns of the SHS export (section 5.1).
COLUMNS = (
    "performance_id", "performance_title", "performer", "language",
    "instrumental", "youtube_url", "work_title",
)

# Strings treated as true in the instrumental column. The export writes
# "True"/"False", but dumps from different quarters have been written
# differently and the cost of tolerance is zero.
_TRUE_VALUES = frozenset({"1", "true", "t", "yes", "y"})

# A sentinel telling "not given" apart from "given as None". Needed because
# tightening condition 2 removes the character alternative, and that has to be
# distinguishable from switching it off explicitly.
AUTO: Any = object()


class Performance(NamedTuple):
    """One performance from the catalogue. The fields after the first three are
    optional, because tests and fixtures describe groups with short tuples while
    the export delivers the full set.
    """
    performer: str
    language: str | None
    instrumental: bool
    performance_id: str = ""
    youtube_url: str = ""
    performance_title: str = ""


@dataclass
class Group:
    """A group of performances sharing a work_title. NOTE: this is not a work, only a string.

    n_vocal and n_total are counted EXACTLY, even when performances is
    truncated. The streaming reader drops from memory the performances of
    groups that will not pass the filter anyway (mega-groups), because keeping
    1,485 performances of "Summertime" only to throw them away straight after
    costs gigabytes across 1.23 million rows. A truncated group has
    truncated=True and no pair may be drawn from it - the filter rejects it
    anyway.
    """
    work_title: str
    performances: list[Performance]
    n_vocal: int | None = None
    n_total: int | None = None
    truncated: bool = False

    def __post_init__(self) -> None:
        self.performances = [
            p if isinstance(p, Performance) else Performance(*p) for p in self.performances
        ]
        if self.n_total is None:
            self.n_total = len(self.performances)
        if self.n_vocal is None:
            self.n_vocal = sum(1 for p in self.performances if not p.instrumental)

    @property
    def vocals(self) -> list[Performance]:
        return [p for p in self.performances if not p.instrumental]

    def vocals_by_language(self) -> dict[str, list[Performance]]:
        """Vocal performances grouped by language. Without a language they cannot be
        paired, because condition 4 requires the same language on both sides.
        """
        by_language: dict[str, list[Performance]] = defaultdict(list)
        for p in self.vocals:
            if p.language:
                by_language[p.language].append(p)
        return dict(by_language)


@dataclass(frozen=True)
class Pair:
    """A pair for calibration. label 1 is a positive (the same work), 0 is a negative.

    For a positive, work_title is the title of the shared group and
    other_work_title is None. For a negative, the two sides come from different
    groups and both fields are filled in.
    """
    work_title: str
    label: int
    kind: str
    language: str | None
    left: Performance
    right: Performance
    other_work_title: str | None = None

    def to_json(self) -> dict:
        return {
            "label": self.label,
            "kind": self.kind,
            "language": self.language,
            "work_title": self.work_title,
            "other_work_title": self.other_work_title,
            "left": _performance_to_json(self.left),
            "right": _performance_to_json(self.right),
        }


@dataclass(frozen=True)
class Sample:
    """The drawn sample. Positives and negatives separately, because they have different source pools."""
    positives: list[Pair] = field(default_factory=list)
    negatives: list[Pair] = field(default_factory=list)
    seed: int = DEFAULT_SEED

    @property
    def pairs(self) -> list[Pair]:
        return [*self.positives, *self.negatives]

    def __len__(self) -> int:
        return len(self.positives) + len(self.negatives)


# --- the filter from section 5.4 --------------------------------------------


def title_is_distinguishable(
    title: str, min_words: int = MIN_WORDS, min_chars: int | None = MIN_CHARS
) -> bool:
    """Condition 2: at least min_words words OR at least min_chars characters."""
    if len(title.split()) >= min_words:
        return True
    return min_chars is not None and len(title) >= min_chars


def _default_min_chars(min_words: int, min_chars: Any) -> int | None:
    """Tightening condition 2 removes the character alternative.

    17 characters is an approximation of three words. At min_words=4 the
    character alternative would let through exactly the titles the tightening is
    meant to cut off (two-word and long ones), so the quality control from
    section 5.4 would change nothing.
    """
    if min_chars is not AUTO:
        return min_chars
    return MIN_CHARS if min_words <= MIN_WORDS else None


def qualifies(
    group: Group,
    min_words: int = MIN_WORDS,
    min_chars: Any = AUTO,
    min_vocals: int = MIN_VOCAL_PERFORMANCES,
    max_vocals: int = MAX_VOCAL_PERFORMANCES,
) -> bool:
    """Whether a positive pair may be drawn from the group. Conditions 1, 2 and 4 of section 5.4."""
    min_chars = _default_min_chars(min_words, min_chars)
    if not (min_vocals <= (group.n_vocal or 0) <= max_vocals):
        return False
    if not title_is_distinguishable(group.work_title, min_words, min_chars):
        return False
    # Condition 4: there must be a language with at least two vocal performances.
    return any(len(v) >= 2 for v in group.vocals_by_language().values())


def pool_from_groups(
    groups: Iterable[Group],
    min_words: int = MIN_WORDS,
    min_chars: Any = AUTO,
    min_vocals: int = MIN_VOCAL_PERFORMANCES,
    max_vocals: int = MAX_VOCAL_PERFORMANCES,
) -> list[Group]:
    """The draw pool for positive pairs. On export_20260701 it gives 69,208 groups."""
    return [
        g for g in groups
        if qualifies(g, min_words, min_chars, min_vocals, max_vocals)
    ]


def negative_pool_from_groups(groups: Iterable[Group]) -> list[Group]:
    """A clean negative pool: works with exactly one performance.

    There are 90,379 such groups in the export. By definition they have no cover
    in the catalogue, so a pair made of two different such works is not labelled
    by assumption but by the absence of any alternative.
    """
    return [g for g in groups if g.n_total == 1]


# --- drawing ----------------------------------------------------------------


def sample_pairs(
    groups: Sequence[Group],
    n_pos: int = DEFAULT_POSITIVES,
    n_neg: int = DEFAULT_NEGATIVES,
    seed: int = DEFAULT_SEED,
    negatives: Sequence[Group] | None = None,
) -> Sample:
    """Draws pairs from the pool after filtering. At most one pair per group (condition 3).

    Without condition 3 half the set would be one work: a group with ten
    performances gives 45 pairs, and drawing pairs instead of groups picks them
    all.

    Negatives come from the singleton pool if one is supplied - otherwise from
    the same pool as the positives, always from two DIFFERENT groups.
    """
    rng = random.Random(seed)
    positives = _draw_positives(groups, n_pos, rng)
    taken = {p.work_title for p in positives}
    negative_source = negatives if negatives is not None else groups
    drawn_negatives = _draw_negatives(negative_source, n_neg, rng, taken)
    return Sample(positives=positives, negatives=drawn_negatives, seed=seed)


def _draw_positives(groups: Sequence[Group], count: int, rng: random.Random) -> list[Pair]:
    if count <= 0:
        return []
    # Sorting before shuffling: the input order depends on the row order in the
    # CSV, while reproducibility must depend on the seed alone.
    candidates = sorted(groups, key=lambda g: g.work_title)
    rng.shuffle(candidates)
    pairs: list[Pair] = []
    for group in candidates:
        if len(pairs) >= count:
            break
        pair = _pair_from_group(group, rng)
        if pair is not None:
            pairs.append(pair)
    return pairs


def _pair_from_group(group: Group, rng: random.Random) -> Pair | None:
    if group.truncated:
        # Truncated groups are mega-groups, which the filter rejects anyway. If
        # someone passed them in bypassing the filter, a pair drawn from an
        # incomplete list would be a quiet untruth about what was drawn from.
        return None
    possible = {lang: v for lang, v in group.vocals_by_language().items() if len(v) >= 2}
    if not possible:
        return None
    language = rng.choice(sorted(possible))
    left, right = rng.sample(sorted(possible[language]), 2)
    return Pair(
        work_title=group.work_title,
        label=1,
        kind="positive",
        language=language,
        left=left,
        right=right,
    )


def _draw_negatives(
    groups: Sequence[Group], count: int, rng: random.Random, taken: set[str],
) -> list[Pair]:
    """Hard negatives: the same performer, different works. Then the same language.

    Random negatives are useless, because the system rejects them trivially and
    the calibration comes out too optimistic. The catalogue carries neither
    tempo nor key nor genre, so the closest available approximation of "the same
    sound" is the same performer, and after that the same language. Structural
    negatives (a shared chord progression without a shared melody) require audio
    and are created only after fetching, outside this script.
    """
    if count <= 0:
        return []
    used = set(taken)
    pairs: list[Pair] = []
    entries = _vocal_entries(groups)

    for index, kind in ((_by_performer(entries), "negative_same_performer"),
                        (_by_language(entries), "negative_same_language")):
        for key in sorted(index):
            if len(pairs) >= count:
                break
            free = [e for e in index[key] if e[0] not in used]
            rng.shuffle(free)
            pair = _pair_from_two_works(free, kind)
            if pair is None:
                continue
            used.add(pair.work_title)
            used.add(pair.other_work_title or "")
            pairs.append(pair)
        if len(pairs) >= count:
            break
    return pairs


def _vocal_entries(groups: Iterable[Group]) -> list[tuple[str, Performance]]:
    """A flat list of (work_title, performance), skipping truncated groups."""
    entries: list[tuple[str, Performance]] = []
    for g in groups:
        if g.truncated:
            continue
        for p in g.performances:
            entries.append((g.work_title, p))
    return sorted(entries)


def _by_performer(entries: list[tuple[str, Performance]]) -> dict[str, list]:
    index: dict[str, list] = defaultdict(list)
    for title, p in entries:
        if p.performer:
            index[p.performer].append((title, p))
    return {k: v for k, v in index.items() if len({t for t, _ in v}) >= 2}


def _by_language(entries: list[tuple[str, Performance]]) -> dict[str, list]:
    index: dict[str, list] = defaultdict(list)
    for title, p in entries:
        if p.language and not p.instrumental:
            index[p.language].append((title, p))
    return {k: v for k, v in index.items() if len({t for t, _ in v}) >= 2}


def _pair_from_two_works(free: list, kind: str) -> Pair | None:
    if len(free) < 2:
        return None
    title_a, left = free[0]
    for title_b, right in free[1:]:
        if title_b == title_a:
            continue
        return Pair(
            work_title=title_a,
            label=0,
            kind=kind,
            language=left.language if left.language == right.language else None,
            left=left,
            right=right,
            other_work_title=title_b,
        )
    return None


# --- reading the export -----------------------------------------------------


class _Accumulator:
    """A group counter while the stream is being read. It counts exactly and remembers little."""

    __slots__ = ("vocal", "other", "n_vocal", "n_total", "truncated")

    def __init__(self) -> None:
        self.vocal: list[Performance] = []
        self.other: list[Performance] = []
        self.n_vocal = 0
        self.n_total = 0
        self.truncated = False

    def add(self, p: Performance, max_vocals: int) -> None:
        self.n_total += 1
        if p.instrumental:
            # Instrumental performances are useful only when they are the sole
            # performance of a work (the negative pool). Outside that case
            # condition 4 rejects them anyway, so there is no point in keeping
            # them.
            if self.n_total == 1:
                self.other.append(p)
            else:
                self.other.clear()
            return
        self.n_vocal += 1
        if self.n_vocal > max_vocals:
            # A mega-group. Condition 1 rejects it, so the performance list is
            # by now nothing but a memory cost. Across 1.23 million rows that is
            # not a detail.
            self.vocal.clear()
            self.truncated = True
            return
        self.vocal.append(p)

    def to_group(self, work_title: str) -> Group:
        performances = list(self.vocal)
        if self.n_total == 1:
            performances += self.other
        return Group(
            work_title=work_title,
            performances=performances,
            n_vocal=self.n_vocal,
            n_total=self.n_total,
            truncated=self.truncated,
        )


@contextmanager
def _open_text(path: str) -> Iterator[io.TextIOBase]:
    """Opens the CSV: a zip with one file inside, a plain file, or stdin ("-").

    The zip is read as a stream, without unpacking to disk. 40 MB of compressed
    export unpacks to a few hundred megabytes that nobody needs.
    """
    if path == "-":
        yield sys.stdin
        return
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not names:
                raise ValueError(f"{path}: there is no .csv file in the archive")
            with zf.open(names[0]) as raw:
                yield io.TextIOWrapper(raw, encoding="utf-8", newline="")
        return
    with open(path, encoding="utf-8", newline="") as file:
        yield file


def _performance_from_row(row: dict) -> Performance:
    language = (row.get("language") or "").strip()
    return Performance(
        performer=(row.get("performer") or "").strip(),
        language=language or None,
        instrumental=(row.get("instrumental") or "").strip().lower() in _TRUE_VALUES,
        performance_id=(row.get("performance_id") or "").strip(),
        youtube_url=(row.get("youtube_url") or "").strip(),
        performance_title=(row.get("performance_title") or "").strip(),
    )


def read_groups(csv_path: str, max_vocals: int = MAX_VOCAL_PERFORMANCES) -> list[Group]:
    """Reads the whole export as a stream and groups performances by work_title.

    Groups exceeding max_vocals come back with exact counters but without the
    performance list (truncated=True) - see the Group docstring.
    """
    accumulators: dict[str, _Accumulator] = {}
    with _open_text(csv_path) as text:
        reader = csv.DictReader(text)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{csv_path}: missing columns {missing}")
        for row in reader:
            title = (row.get("work_title") or "").strip()
            if not title:
                continue
            accumulator = accumulators.get(title)
            if accumulator is None:
                accumulator = accumulators[title] = _Accumulator()
            accumulator.add(_performance_from_row(row), max_vocals)
    return [a.to_group(t) for t, a in accumulators.items()]


def pool(csv_path: str, min_words: int = MIN_WORDS, min_chars: Any = AUTO) -> list[Group]:
    """The draw pool straight from the export. On export_20260701: 69,208 groups."""
    return pool_from_groups(read_groups(csv_path), min_words=min_words, min_chars=min_chars)


# --- output -----------------------------------------------------------------


def _performance_to_json(p: Performance) -> dict:
    # The keys "id" and "url" are the ones fetch_audio._identifier and
    # fetch_audio._url look for. The rest is for the human doing quality control.
    return {
        "id": p.performance_id,
        "url": p.youtube_url,
        "performer": p.performer,
        "language": p.language,
        "instrumental": p.instrumental,
        "performance_title": p.performance_title,
    }


def fetch_items(sample: Sample) -> list[dict]:
    """Entries for fetch_audio.fetch_many, one per performance, without repetitions.

    A performance may occur in several pairs (the same performer across several
    negatives), and there is no point in fetching it a second time.
    """
    items: dict[str, dict] = {}
    for pair in sample.pairs:
        for p in (pair.left, pair.right):
            key = p.performance_id or p.youtube_url
            if key and key not in items:
                items[key] = {"id": p.performance_id or key, "url": p.youtube_url}
    return list(items.values())


def to_json(
    sample: Sample,
    csv_path: str,
    pool_size: int,
    negative_pool_size: int,
    min_words: int,
    min_chars: int | None,
    target_pos: int,
    target_neg: int,
    overshoot: float,
) -> dict:
    return {
        "source_csv": os.path.basename(csv_path),
        "seed": sample.seed,
        "filter": {
            "min_vocal_performances": MIN_VOCAL_PERFORMANCES,
            "max_vocal_performances": MAX_VOCAL_PERFORMANCES,
            "min_title_words": min_words,
            "min_title_chars": min_chars,
            "one_pair_per_group": True,
            "same_language_both_sides": True,
        },
        "pool_groups": pool_size,
        "negative_pool_groups": negative_pool_size,
        "target": {"positives": target_pos, "negatives": target_neg},
        "surplus": overshoot,
        "drawn": {"positives": len(sample.positives), "negatives": len(sample.negatives)},
        # Listening to 20 positive pairs is mandatory (section 5.4) and is done
        # by a human. The field stays empty until that happens - a missing entry
        # has to be visible rather than assumed.
        "manual_qa": {"listened_pairs": 0, "wrong_pairs": None, "report": None},
        "pairs": [p.to_json() for p in sample.pairs],
    }


def _default_overshoot() -> float:
    """A 25% overshoot relative to the target (section 5.7). The constant lives in fetch_audio."""
    try:
        from scripts.fetch_audio import OVERSHOOT

        return float(OVERSHOOT)
    except Exception:  # noqa: BLE001 - the scripts package missing from the path is not a fatal error
        return 1.25


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Draws a calibration sample from the SHS export.")
    parser.add_argument("--csv", default=os.environ.get("ORIGIN_SHS_EXPORT", DEFAULT_EXPORT),
                        help='path to the export (.csv.zip, .csv or "-" for stdin)')
    parser.add_argument("--out", default=DEFAULT_OUTPUT)
    parser.add_argument("--n-pos", type=int, default=DEFAULT_POSITIVES)
    parser.add_argument("--n-neg", type=int, default=DEFAULT_NEGATIVES)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--min-words", type=int, default=MIN_WORDS,
                        help="tightening of condition 2 from section 5.4 (quality control)")
    parser.add_argument("--overshoot", type=float, default=None,
                        help="how many times more pairs to draw than needed (section 5.7)")
    args = parser.parse_args(argv)

    overshoot = args.overshoot if args.overshoot is not None else _default_overshoot()
    min_chars = _default_min_chars(args.min_words, AUTO)

    all_groups = read_groups(args.csv)
    positive_pool = pool_from_groups(all_groups, min_words=args.min_words, min_chars=min_chars)
    negative_pool = negative_pool_from_groups(all_groups)

    sample = sample_pairs(
        positive_pool,
        n_pos=math.ceil(args.n_pos * overshoot),
        n_neg=math.ceil(args.n_neg * overshoot),
        seed=args.seed,
        negatives=negative_pool,
    )

    result = to_json(
        sample, args.csv, len(positive_pool), len(negative_pool),
        args.min_words, min_chars, args.n_pos, args.n_neg, overshoot,
    )
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"groups in the catalogue: {len(all_groups)}\n"
        f"pool after the 5.4 filter: {len(positive_pool)}\n"
        f"negative pool (singletons): {len(negative_pool)}\n"
        f"drawn: {len(sample.positives)} positives, {len(sample.negatives)} negatives\n"
        f"written: {path}\n"
        f"STILL TO DO: listen to 20 positive pairs (section 5.4) -> docs/sample-quality-control.md"
    )
    return 0


if __name__ == "__main__":
    # Running this as a script does not put the repository on the import path,
    # and _default_overshoot reaches for a constant from scripts.fetch_audio.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    raise SystemExit(main())
