"""The legal layer: evidentiary flags and classification, never a ruling. Section 11.

The module translates the fusion result into the `Legal` block of section 11.3.
Every rule here has its basis written next to the code, because this is the
only place in the system where a technical signal meets a legal concept:

- the Polish Act of 4 February 1994 on Copyright and Related Rights: art. 1
  (a work), art. 2(1) (a derivative work), art. 2(4) (inspiration), chapter 11
  (phonograms and artistic performances),
- Pelham I, CJEU judgment of 29 July 2019, C-476/17 - recognisability of a
  sample to the ear as the limit of the phonogram producer's right,
- Pelham II, CJEU judgment of 14 April 2026, C-590/23 - the three cumulative
  conditions of pastiche against art. 5(3)(k) of Directive 2001/29/EC.

Of the three conditions of pastiche the system measures two: the reference and
its recognisability (`recognizability`) and the perceptible difference
(`modification`). The third one, a recognisable artistic dialogue, it does not
measure and will not measure - that is a declared boundary of the tool, not a
gap. High modification is NOT a green light: Pelham II leaves hidden imitation
and plagiarism outside the exception.
"""
from __future__ import annotations

import math

from origin.contracts import (
    Candidate,
    FingerprintResult,
    Legal,
    RightsLayer,
    VerdictClass,
)
from origin.fusion import Verdict


# Section 11.3 knows exactly two risk flags and both are in English. The same
# strings are read by the API stub (src/origin/api/mock.py), so that the
# frontend does not have to maintain a translation dictionary between demo mode
# and real mode.
FLAG_RECOGNIZABLE_EXCERPT = "recognizable_excerpt"
FLAG_POSSIBLE_PASTICHE = "possible_pastiche"

EXCERPT_CLASSES: tuple[VerdictClass, ...] = ("EXCERPT_PHONOGRAM", "EXCERPT_WORK")

# Prefixes of licence identifiers that permit use. Besides the Creative Commons
# family this includes the public domain, because the catalogue contains MUSAN,
# where part of the material is exactly that
# (docs/references/license-status-source.md).
OPEN_LICENSE_PREFIXES = ("cc", "public_domain")

# Flag thresholds. They are not in config.THRESHOLDS, because that dictionary
# holds the decision-tree thresholds of section 9.2, whereas these two numbers
# do not decide the class, only what the legal panel highlights. The values are
# shared with the API stub and reproduce the example from section 11.3
# (recognizability 0.78, modification 0.41 - both flag rows).
RECOGNIZABLE_THRESHOLD = 0.50
# Pastiche requires BOTH things at once: a perceptible difference from the
# source and a still recognisable reference. A high modification score alone
# with low recognisability is not a borderline situation, just different
# material.
PASTICHE_MODIFICATION_THRESHOLD = 0.40
PASTICHE_RECOGNIZABILITY_THRESHOLD = 0.70

# Normalisation scales of the modification score. An octave and a doubling of
# tempo are a full departure from the original on that axis; anything above is
# clipped anyway.
SEMITONES_PER_OCTAVE = 12.0


def rights_layers(verdict_class: str) -> list[RightsLayer]:
    """The full set of rights layers the match touches. Section 11.1.

    This is NOT the same as `RankingEntry.verdict_layer`, which carries one
    leading layer. `VERSION` is the same work recorded in a different
    performance, so it touches the work (art. 1) and the artistic performance
    (chapter 11) at once, and those two layers have different rightholders and
    different terms of protection.
    """
    if verdict_class in ("EXACT", "MODIFIED", "EXCERPT_PHONOGRAM"):
        return ["phonogram"]
    if verdict_class == "VERSION":
        return ["work", "performance"]
    if verdict_class in ("EXCERPT_WORK", "LYRICS"):
        return ["work"]
    # COMMON and NONE touch no rights layer: a common element and inspiration
    # are not objects of protection (art. 1(1) in conjunction with art. 2(4)).
    return []


def recognizability(fp: FingerprintResult | None) -> float | None:
    """Recognisability of the fragment to the ear, derived from `A.peak_ratio`. Pelham I.

    Returns None when detector A computed nothing. Zero would mean "we checked
    and the fragment is unrecognisable", which is exactly the claim that must
    not be made when the detector was rejected (section 7.0).
    """
    if fp is None or fp.status != "ok" or fp.peak_ratio is None:
        return None
    return min(max(float(fp.peak_ratio), 0.0), 1.0)


def modification(fp: FingerprintResult | None) -> float | None:
    """The degree of departure from the original, the second condition of pastiche. Pelham II.

    Computed from detector A's `transform`, that is from the key and tempo
    shift. Spectral filtering and loop length from section 11.2 have no carrier
    in the `FingerprintResult` contract yet and will join once the detector
    starts returning them.

    A missing `transform` on a computed fingerprint is a measured zero: the
    match was made without shifting key or tempo. A missing measurement
    altogether is None.
    """
    if fp is None or fp.status != "ok":
        return None
    transform = fp.transform or {}

    # Each axis separately on a 0..1 scale, then a probabilistic sum: a second
    # change adds difference, but no number of changes will exceed a full
    # departure.
    axes = (
        _key_axis(transform.get("semitones")),
        _tempo_axis(transform.get("tempo_ratio")),
    )
    remaining = 1.0
    for axis in axes:
        remaining *= 1.0 - axis
    return round(1.0 - remaining, 4)


def _key_axis(semitones: float | None) -> float:
    """A shift by an octave is treated as a full departure on this axis."""
    if semitones is None:
        return 0.0
    return min(abs(float(semitones)) / SEMITONES_PER_OCTAVE, 1.0)


def _tempo_axis(ratio: float | None) -> float:
    """A logarithmic scale, because tempo is heard as a proportion, not a difference.

    Speeding up by 6% and slowing down by 6% are the same audible change, so
    they count the same. A doubling or a halving of tempo is a full departure.
    """
    if ratio is None or ratio <= 0.0:
        return 0.0
    return min(abs(math.log2(float(ratio))), 1.0)


def _is_open_license(candidate: Candidate) -> bool:
    return candidate.license.startswith(OPEN_LICENSE_PREFIXES)


def _license_name(identifier: str) -> str:
    """`cc-by-nc-sa-3.0` -> `CC BY-NC-SA 3.0`. The text goes to the user's clipboard."""
    parts = identifier.split("-")
    if parts and parts[-1][:1].isdigit():
        version = f" {parts[-1]}"
        parts = parts[:-1]
    else:
        version = ""
    if len(parts) > 1:
        return f"{parts[0].upper()} {'-'.join(p.upper() for p in parts[1:])}{version}"
    return f"{identifier.upper()}{version}"


def attribution(candidate: Candidate) -> str | None:
    """A ready-made attribution for an open licence. Section 11.2.

    For a restricted licence and for an unknown one it returns None, and those
    are two different Nones: the first means "attribution settles nothing, a
    permission is needed", the second "we do not know what the licence
    requires". They are told apart by `license_status`, which the UI has to
    show alongside (section 11.3).
    """
    if not _is_open_license(candidate):
        return None
    return f'{candidate.artist}, "{candidate.name}", {_license_name(candidate.license)}'


def risk_flags(
    verdict_class: str,
    recognizability_value: float | None,
    modification_value: float | None,
    candidate: Candidate,
) -> list[str]:
    """Table 11.2. Most rows say "no flag" and that is not a mistake.

    A flag is an exceptional signal, not an ornament attached to every result.
    A common element, inspiration and a candidate under an open licence get
    none.
    """
    # The licence permits use, so there is no risk to report - instead of a
    # flag the system generates an attribution. Note: this applies ONLY to a
    # licence that is known and open. "unknown" is missing information, never
    # an absence of restrictions.
    if _is_open_license(candidate):
        return []
    # Outside the EXCERPT classes there is nothing to talk about: the question
    # of a short sample's recognisability is only asked about a sample
    # (Pelham I).
    if verdict_class not in EXCERPT_CLASSES:
        return []

    recognisability_score = recognizability_value or 0.0
    modification_score = modification_value or 0.0

    flags: list[str] = []
    # Pelham I: a phonogram producer may prohibit taking even a very short
    # sample, unless it was incorporated in a form unrecognisable to the ear.
    if recognisability_score >= RECOGNIZABLE_THRESHOLD:
        flags.append(FLAG_RECOGNIZABLE_EXCERPT)
    # Pelham II: "high modification with recognisability preserved is a
    # borderline situation and is to be flagged as such" (section 11.2). The
    # flag says "this may be a pastiche, check the third condition", not "this
    # is a pastiche".
    if (
        modification_score >= PASTICHE_MODIFICATION_THRESHOLD
        and recognisability_score >= PASTICHE_RECOGNIZABILITY_THRESHOLD
    ):
        flags.append(FLAG_POSSIBLE_PASTICHE)
    return flags


def assess(
    verdict: Verdict,
    fp: FingerprintResult | None,
    candidate: Candidate,
) -> Legal:
    """The legal block for one ranking entry. Section 11.3.

    `disclaimer` is not set here: its fixed text lives in the `Legal` contract,
    so that it has a single source and a result cannot be built without it.
    """
    verdict_class = verdict.verdict_class
    excerpt = verdict_class in EXCERPT_CLASSES
    # Both scores are concepts from the Pelham test, that is from the question
    # about a sample. For other classes they mean nothing and stay empty,
    # rather than reporting a number the panel would not know how to interpret.
    recognisability_score = recognizability(fp) if excerpt else None
    modification_score = modification(fp) if excerpt else None
    return Legal(
        rights_layer=rights_layers(verdict_class),
        risk_flags=risk_flags(verdict_class, recognisability_score, modification_score, candidate),
        recognizability=recognisability_score,
        modification=modification_score,
        # The licence status does not follow from audio analysis: it is a
        # separate metadata layer, copied from the manifest without
        # interpretation.
        license_status=candidate.license,
        required_attribution=attribution(candidate),
    )
