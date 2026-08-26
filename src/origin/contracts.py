"""JSON contracts for the whole system. Sections 7.0 and 12 of the specification."""
from typing import Annotated, Any, Literal, Union, get_args

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializeAsAny,
    field_validator,
    model_validator,
)

DetectorStatus = Literal["ok", "not_applicable", "gated", "failed"]
# One source of truth: the tuple is derived from the type, not written next to
# it. A hand-maintained copy would let someone add a value in one place only
# and still pass the whole suite.
DETECTOR_STATUSES = get_args(DetectorStatus)

VerdictClass = Literal[
    "EXACT", "MODIFIED", "VERSION",
    "EXCERPT_PHONOGRAM", "EXCERPT_WORK",
    "LYRICS", "COMMON", "NONE",
]
VERDICT_CLASSES = get_args(VerdictClass)

RightsLayer = Literal["phonogram", "work", "performance"]
PublishedSource = Literal["manual", "metadata_registry"]
ProbabilityStatus = Literal["calibrated", "uncalibrated"]
ResultStatus = Literal["partial", "final", "failed"]
StageStatus = Literal["running", "done", "partial", "final", "gated", "failed"]

# Fields that are not a claim about measured similarity, so they are allowed to
# exist under any status: identification, rejection reason, detected language
# and the separation-run flag.
_NON_MEASUREMENT_FIELDS = frozenset({
    "detector", "candidate_id", "status", "reason", "language", "used_separation",
})


_MISSING = object()


class _AtomicAssignment(BaseModel):
    """A model where an assignment either passes validation or changes nothing.

    With validate_assignment, pydantic sets the field first and only then runs
    the model validator. After a caught ValidationError the object would stay
    in a state forbidden by the contract and on the next model_dump would
    serialise the very lie the validator was meant to prevent. We roll the
    change back.
    """

    model_config = ConfigDict(validate_assignment=True)

    def __setattr__(self, name: str, value: Any) -> None:
        previous = self.__dict__.get(name, _MISSING)
        fields_set = set(self.__pydantic_fields_set__)
        try:
            super().__setattr__(name, value)
        except Exception:
            if previous is _MISSING:
                self.__dict__.pop(name, None)
            else:
                self.__dict__[name] = previous
            object.__setattr__(self, "__pydantic_fields_set__", fields_set)
            raise


class DetectorResult(_AtomicAssignment):
    """The result for a single candidate. Status defaults to ok - see section 7.0."""

    # Validation on assignment, because natural detector code computes first
    # and sets the status later. Without it, r.status = "gated" on a computed
    # result creates an object that breaks the contract and nobody finds out.
    detector: Literal["generic"] = "generic"
    candidate_id: str
    status: DetectorStatus = "ok"
    reason: str | None = None

    def carries_claim(self) -> str | None:
        """The name of the first field that claims something about a measurement, or None.

        A claim is **any value different from the default**, not just a
        non-zero number. jaccard=0.0 with a rejected transcript means "textual
        similarity is zero", which is exactly the lie section 7.0 guards
        against. The same goes for transform={...} or matched_spans=[...]: the
        carrier does not matter, what matters is that the field claims
        something.
        """
        for name, field in type(self).model_fields.items():
            if name in _NON_MEASUREMENT_FIELDS:
                continue
            if getattr(self, name) != field.get_default(call_default_factory=True):
                return name
        return None

    @model_validator(mode="after")
    def _not_applicable_is_not_zero(self) -> "DetectorResult":
        """Section 7.0: not_applicable and gated are not zero.

        Zero means "we checked and there is no similarity". Under any status
        other than ok we checked nothing, so no measurement field is allowed to
        exist - in an evidentiary tool that would be a lie. We enforce it in
        the contract so that a mistake ends in a validation error rather than a
        quiet number in the interface.
        """
        if self.status == "ok":
            return self
        name = self.carries_claim()
        if name is not None:
            raise ValueError(
                f"field '{name}' carries a value with status='{self.status}'; "
                f"not applicable and rejected by a gate are not zero"
            )
        return self


class FingerprintResult(DetectorResult):
    detector: Literal["fingerprint"] = "fingerprint"
    matched_hashes: int | None = None
    peak_ratio: float | None = None
    query_span: tuple[float, float] | None = None
    candidate_span: tuple[float, float] | None = None
    offset: float | None = None
    repetitions: int = 0
    transform: dict[str, float] | None = None

    @property
    def span_length(self) -> float | None:
        """Length of the matched segment, or None when the span is unknown.

        Returning 0.0 for an unknown span would break fusion rule 3: the
        condition span_length < EXACT_MIN_SPAN_S would be satisfied by a result
        that says nothing about length. Fusion has to handle None explicitly.
        """
        if self.query_span is None:
            return None
        return self.query_span[1] - self.query_span[0]


class HarmonicResult(DetectorResult):
    detector: Literal["harmonic"] = "harmonic"
    qmax_score: float | None = None
    transposition: int | None = None
    tempo_ratio: float | None = None
    alignment_path: list[tuple[int, int]] = Field(default_factory=list)
    coverage: float | None = None
    chord_sequence: list[str] = Field(default_factory=list)


class LyricsResult(DetectorResult):
    detector: Literal["lyrics"] = "lyrics"
    jaccard: float | None = None
    semantic_sim: float | None = None
    # One dict per common run: `query_len` and `candidate_len` (character
    # lengths), `query_time` ([start, end] in the query, or null when the
    # transcript carried no times) and `idf`. No lyric text - not here and not
    # anywhere downstream. These results are dumped whole onto the public SSE
    # stream, and the two texts being compared are a copyrighted recording's
    # lyrics and a transcript of the user's material. A length says how much
    # matched; it does not reproduce it.
    matched_spans: list[dict[str, Any]] = Field(default_factory=list)
    asr_confidence: float | None = None
    language: str | None = None
    used_separation: bool = False


class MelodicResult(DetectorResult):
    detector: Literal["melodic"] = "melodic"
    matched_ngrams: list[dict[str, Any]] = Field(default_factory=list)
    longest_common_run: int = 0
    ms_distance: float | None = None
    # Whether the query melody was transcribed from the separated vocal track
    # (section 7.4 step 1) or from the full mix. False is the cheap path, not a
    # missing value: it means detector D's gate passed on the first pass, so no
    # separation existed to share and basic-pitch saw drums and accompaniment
    # alongside the voice. The number below has to be read differently in the
    # two cases, so the flag travels with it rather than being inferred.
    used_separation: bool = False


# A union discriminated by the detector field. Without it, reading is lossy: a
# field typed as the base class would build a base DetectorResult from JSON and
# quietly drop peak_ratio, and level 1 envelopes travel through the job store on
# their way to level 2 fusion, so they really do cross a JSON boundary.
AnyDetectorResult = Annotated[
    Union[
        FingerprintResult,
        HarmonicResult,
        LyricsResult,
        MelodicResult,
        DetectorResult,
    ],
    Field(discriminator="detector"),
]

_RESULT_TAGS = frozenset({"fingerprint", "harmonic", "lyrics", "melodic"})


class DetectorEnvelope(_AtomicAssignment):
    """The envelope status covers the run for the whole query, not for one candidate."""

    detector: str
    status: DetectorStatus = "ok"
    reason: str | None = None
    # SerializeAsAny in case of a subclass outside the union: the dump has to
    # follow the object's class, not the field's schema.
    results: list[SerializeAsAny[AnyDetectorResult]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _fill_in_result_tag(cls, data: Any) -> Any:
        """A result without a detector field takes the tag from the envelope.

        Section 7.0 shows a result written as {"candidate_id": "cand_07"},
        without a tag. A discriminated union requires a tag, so we add it from
        the envelope's detector name instead of breaking the contract from the
        specification.
        """
        if not isinstance(data, dict):
            return data
        results = data.get("results")
        if not isinstance(results, list):
            return data
        name = data.get("detector")
        tag = name if name in _RESULT_TAGS else "generic"
        return {
            **data,
            "results": [
                {**r, "detector": tag}
                if isinstance(r, dict) and "detector" not in r
                else r
                for r in results
            ],
        }

    @model_validator(mode="after")
    def _envelope_carries_no_numbers_either(self) -> "DetectorEnvelope":
        """Section 7.0 puts both status levels on an equal footing.

        A gated envelope holding a result that carries jaccard=0.83 would show
        a number next to the words "rejected by the confidence gate".
        """
        if self.status == "ok":
            return self
        for result in self.results:
            name = result.carries_claim()
            if name is not None:
                raise ValueError(
                    f"result '{result.candidate_id}' carries field '{name}' with "
                    f"envelope status '{self.status}'; the whole detector run "
                    f"was not computed"
                )
        return self


class Candidate(BaseModel):
    id: str
    name: str
    artist: str
    shs_performance_id: str | None = None
    source_url: str
    # Path on the server's disk. It stays in the contract because the detectors
    # work on it, but the browser has no way to play it. Playback uses
    # audio_url, added by the API layer - the manifest does not contain it.
    audio_path: str
    # The address under which the API will serve this recording (section 12).
    # None means: the file is not on disk, so there is nothing to play. We do
    # not substitute any placeholder audio, because in an evidentiary tool a
    # stand-in is worse than nothing.
    audio_url: str | None = None
    # published and published_source are optional on purpose: the chronology
    # rule from 9.3 applies only to candidates that have a date, so a missing
    # date is a valid state rather than missing data.
    published: str | None = None
    published_source: PublishedSource | None = None
    license: str = "unknown"
    instrumental: bool = False
    language: str | None = None
    lyrics_path: str | None = None

    @field_validator("published_source", mode="before")
    @classmethod
    def _reject_youtube(cls, v: Any) -> Any:
        """Section 5.5: the YouTube upload date is not the release date."""
        if v == "youtube":
            raise ValueError(
                "published_source 'youtube' is forbidden: the upload date is "
                "not the release date and the chronology axis would point at "
                "the cover as the original"
            )
        return v


class CandidateSet(BaseModel):
    """The manifest data/candidates/<set_id>.json. Section 5.3, a manually curated artifact."""
    set_id: str
    candidates: list[Candidate] = Field(default_factory=list)


class Alignment(BaseModel):
    """Where and how the query was aligned to the candidate. Section 12.

    All fields optional: a match based on lyrics alone has no time alignment,
    and a fingerprint match has no transposition.
    """
    query_span: tuple[float, float] | None = None
    candidate_span: tuple[float, float] | None = None
    transposition: int | None = None
    tempo_ratio: float | None = None


class Commonality(BaseModel):
    """The commonality filter, section 8. Numbers optional, because a corpus may not exist."""
    mean_idf: float | None = None
    corpus_frequency: int | None = None
    corpus_size: int | None = None


class Legal(BaseModel):
    """Evidentiary flags, never a ruling on infringement. Section 11.3."""
    # The full set of rights layers the match concerns. VERSION gets
    # ["work", "performance"] here, while RankingEntry.verdict_layer carries
    # only the leading layer.
    rights_layer: list[RightsLayer] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    recognizability: float | None = None
    modification: float | None = None
    # unknown must be displayed as missing information, never as absence of restrictions.
    license_status: str = "unknown"
    required_attribution: str | None = None
    disclaimer: str = "Technical signal, not legal advice."


class Evidence(BaseModel):
    """A summary of the 7.0 envelope attached to a ranking entry.

    The frontend must not assume the detector returned a number, so the status
    is mandatory here and uses the same vocabulary as the envelope.
    """
    status: DetectorStatus = "ok"
    reason: str | None = None


class QueryInfo(BaseModel):
    duration: float
    waveform_url: str | None = None
    transcript: list[dict[str, Any]] = Field(default_factory=list)


class RankingEntry(BaseModel):
    rank: int
    candidate: Candidate
    verdict_class: VerdictClass
    # The LEADING layer, deliberately singular. The full set of layers is
    # carried by Legal.rights_layer (VERSION: ["work", "performance"]). None is
    # valid: COMMON and NONE concern no rights layer at all (section 3).
    verdict_layer: RightsLayer | None = None
    probability: float | None = None
    # Section 10.5: the UI must tell a model probability apart from a raw score.
    probability_status: ProbabilityStatus
    evidence: dict[str, Evidence] = Field(default_factory=dict)
    alignment: Alignment | None = None
    commonality: Commonality | None = None
    # Section 12 shows "legal": {}. An empty Legal is the valid state "we know
    # nothing", so null must never appear on the wire.
    legal: Legal = Field(default_factory=Legal)
    explanation: str = ""

    @field_validator("legal", mode="before")
    @classmethod
    def _missing_legal_is_empty_legal(cls, v: Any) -> Any:
        if v is None:
            return Legal()
        return v


class CalibrationInfo(BaseModel):
    """Section 10. The absence of this object means: no model exists, the numbers are raw."""

    # The name model_version comes straight from section 12 and stays; we only
    # switch off pydantic's protection of the model_ prefix so it stops warning.
    model_config = ConfigDict(protected_namespaces=())

    model_version: str
    trained_on: int
    precision_at_threshold: float | None = None


class AnalyzeResult(BaseModel):
    status: ResultStatus
    completed_levels: list[int] = Field(default_factory=list)
    query: QueryInfo
    ranking: list[RankingEntry] = Field(default_factory=list)
    calibration: CalibrationInfo | None = None


class StreamEvent(BaseModel):
    """The SSE event from section 12. A gated status with a next field in detail is content, not an error."""
    stage: str
    level: int
    status: StageStatus
    detail: dict[str, Any] = Field(default_factory=dict)
