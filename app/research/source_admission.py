"""Deterministic source admission for a C5-eligible ARTICLE research corpus.

Holding three retrieval IDs is not evidence.  This module answers one narrow
question before a Research Card may support an article: do the admitted
sources actually constitute independent support for every confirmed claim?

Everything that can change the lifecycle is decided here from persisted
metadata, never from a model's self-description.  A model may propose the
classification of a source, but an unclassified or unknown source fails
closed and requires an explicit operator or fixture classification.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from urllib.parse import urlsplit

from app.content.foundation import canonical_json, sha256_text


SOURCE_ADMISSION_POLICY_VERSION = "source_admission_policy_v1"

# Reason codes.  They are stable strings because they end up in the Research
# Card rejection reason and in durable evaluation findings.
TOO_FEW_ADMITTED_SOURCES = "TOO_FEW_ADMITTED_SOURCES"
INSUFFICIENT_SOURCE_INDEPENDENCE = "INSUFFICIENT_SOURCE_INDEPENDENCE"
SYNDICATED_DUPLICATE_SOURCES = "SYNDICATED_DUPLICATE_SOURCES"
NO_PRIMARY_SOURCE = "NO_PRIMARY_SOURCE"
ORIENTATION_ONLY_CORPUS = "ORIENTATION_ONLY_CORPUS"
SOURCE_CLASSIFICATION_UNKNOWN = "SOURCE_CLASSIFICATION_UNKNOWN"
STALE_TIME_SENSITIVE_CORPUS = "STALE_TIME_SENSITIVE_CORPUS"
# Recorded, never a rejection reason: it says the corpus could not be aged, not
# that it is old.
FRESHNESS_UNVERIFIABLE = "FRESHNESS_UNVERIFIABLE"
CLAIM_WITHOUT_ADMITTED_EVIDENCE = "CLAIM_WITHOUT_ADMITTED_EVIDENCE"
SYNDICATION_METADATA_INVALID = "SYNDICATION_METADATA_INVALID"

# A syndication chain is followed to a small, fixed depth so that
# A->B->C collapses onto C instead of leaving three "owners".
MAX_SYNDICATION_CHAIN_DEPTH = 4


class SourceClass(str, Enum):
    """How much independent weight one source may carry.

    PRIMARY      - the originating record: filing, dataset, ruling, paper,
                   official statistic, first-party statement.
    SUPPORTING   - independent reporting or analysis about the subject.
    ORIENTATION  - encyclopaedic or aggregated overview.  Useful to orient a
                   reader; never sufficient on its own for a factual claim.
    """

    PRIMARY = "PRIMARY"
    SUPPORTING = "SUPPORTING"
    ORIENTATION = "ORIENTATION"


# Hosts whose content is encyclopaedic/aggregated by construction.  Being on
# this list caps a source at ORIENTATION even if it was declared otherwise;
# it never promotes anything.
ORIENTATION_HOSTS: frozenset[str] = frozenset({
    "wikipedia.org",
    "m.wikipedia.org",
    "simple.wikipedia.org",
    "wikimedia.org",
    "wikidata.org",
    "britannica.com",
})

# Suffixes that are public registries rather than registrable owners.  Used to
# derive the independence key, so "a.example.co.uk" and "b.example.co.uk" are
# one owner, not two.
_MULTI_LABEL_PUBLIC_SUFFIXES: frozenset[str] = frozenset({
    "co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "net.au", "org.au",
    "co.jp", "or.jp", "ne.jp", "com.br", "com.pl", "org.pl", "gov.pl",
    "co.nz", "co.za", "com.cn", "org.cn", "gov.cn", "co.in", "gov.in",
})


class SourceAdmissionError(ValueError):
    """A source descriptor is malformed and cannot be admitted or rejected."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class SourceDescriptor:
    """One candidate source with the metadata admission is allowed to trust.

    ``source_class`` and ``published_at`` come from persisted, operator- or
    fixture-supplied classification.  ``content_sha256`` is the canonical text
    hash already produced by the E1 retrieval recorder, so syndicated copies
    of the same article collapse without any semantic judgement.
    """

    url: str
    retrieval_id: int
    source_class: SourceClass | None = None
    published_at: datetime | None = None
    content_sha256: str | None = None
    syndication_of: str | None = None
    supports_claim: str | None = None

    @property
    def host(self) -> str:
        return registrable_host(self.url)

    @property
    def declared_origin_host(self) -> str | None:
        """Owner-level host of a declared syndication origin, or ``None``.

        The declaration is canonicalized through exactly the same function as
        an ordinary source URL, so ``https://www.origin.com/a/``, ``origin.com``
        and ``http://news.origin.com/b?x=1`` all resolve to one owner instead of
        minting three new "independent" ones.  An unparseable declaration is not
        silently treated as a new owner: it raises and the caller fails closed.
        """
        if not self.syndication_of or not self.syndication_of.strip():
            return None
        return registrable_host(self.syndication_of)

    @property
    def independence_key(self) -> str:
        """Two sources sharing this key are never two independent sources."""
        origin = self.declared_origin_host
        return origin if origin is not None else self.host


@dataclass(frozen=True)
class SourceAdmissionPolicy:
    """The deterministic thresholds one ARTICLE corpus must satisfy."""

    policy_version: str = SOURCE_ADMISSION_POLICY_VERSION
    min_admitted_sources: int = 3
    min_independent_owners: int = 2
    require_primary_source: bool = True
    max_orientation_share: float = 0.5
    freshness_max_age_days: int = 540

    def payload(self) -> dict[str, object]:
        return {
            "policy_version": self.policy_version,
            "min_admitted_sources": self.min_admitted_sources,
            "min_independent_owners": self.min_independent_owners,
            "require_primary_source": self.require_primary_source,
            "max_orientation_share": self.max_orientation_share,
            "freshness_max_age_days": self.freshness_max_age_days,
        }

    def fingerprint(self) -> str:
        return sha256_text(canonical_json(self.payload()))


@dataclass(frozen=True)
class AdmittedSource:
    url: str
    retrieval_id: int
    source_class: SourceClass
    independence_key: str

    def payload(self) -> dict[str, object]:
        return {
            "url": self.url,
            "retrieval_id": self.retrieval_id,
            "source_class": self.source_class.value,
            "independence_key": self.independence_key,
        }


@dataclass(frozen=True)
class SourceAdmissionOutcome:
    admitted: bool
    reasons: tuple[str, ...] = ()
    findings: tuple[dict[str, object], ...] = ()
    admitted_sources: tuple[AdmittedSource, ...] = ()
    independent_owner_count: int = 0
    policy_fingerprint: str = ""

    def payload(self) -> dict[str, object]:
        return {
            "admitted": self.admitted,
            "reasons": list(self.reasons),
            "findings": [dict(item) for item in self.findings],
            "admitted_sources": [item.payload() for item in self.admitted_sources],
            "independent_owner_count": self.independent_owner_count,
            "policy_fingerprint": self.policy_fingerprint,
        }

    def fingerprint(self) -> str:
        return sha256_text(canonical_json(self.payload()))


def registrable_host(url: str) -> str:
    """Owner-level host: strip scheme, port, userinfo, ``www`` and subdomains."""
    if not isinstance(url, str) or not url.strip():
        raise SourceAdmissionError(
            "SOURCE_URL_INVALID", "Source URL must be a non-empty string.",
        )
    candidate = url.strip()
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    host = (urlsplit(candidate).hostname or "").lower().strip(".")
    if not host:
        raise SourceAdmissionError(
            "SOURCE_URL_INVALID", f"Source URL has no host: {url!r}.",
        )
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    tail_two = ".".join(labels[-2:])
    if tail_two in _MULTI_LABEL_PUBLIC_SUFFIXES:
        return ".".join(labels[-3:])
    return tail_two


def resolve_independence_keys(
    descriptors: Sequence[SourceDescriptor],
) -> dict[int, str]:
    """Map each retrieval to the owner it may count for, chains collapsed.

    A declared syndication origin is canonicalized with ``registrable_host``, so
    scheme, ``www``, path, query and trailing slash cannot manufacture a new
    owner.  When the declared origin is itself present in this corpus and also
    declares an origin, the chain is followed to a fixed depth; a cycle or an
    unparseable declaration raises so the caller fails closed.
    """
    direct: dict[int, str] = {}
    origin_of_host: dict[str, str] = {}
    for descriptor in descriptors:
        try:
            host = descriptor.host
            declared = descriptor.declared_origin_host
        except SourceAdmissionError as exc:
            raise SourceAdmissionError(
                "SYNDICATION_METADATA_INVALID",
                f"source {descriptor.url!r} has unusable identity metadata: {exc}",
            ) from exc
        direct[descriptor.retrieval_id] = declared if declared is not None else host
        if declared is not None and declared != host:
            existing = origin_of_host.get(host)
            if existing is not None and existing != declared:
                raise SourceAdmissionError(
                    "SYNDICATION_METADATA_INVALID",
                    f"host {host!r} declares two different syndication origins.",
                )
            origin_of_host[host] = declared

    resolved: dict[int, str] = {}
    for retrieval_id, start in direct.items():
        seen = {start}
        key = start
        for _ in range(MAX_SYNDICATION_CHAIN_DEPTH):
            nxt = origin_of_host.get(key)
            if nxt is None or nxt == key:
                break
            if nxt in seen:
                raise SourceAdmissionError(
                    "SYNDICATION_METADATA_INVALID",
                    f"syndication declarations form a cycle at {nxt!r}.",
                )
            seen.add(nxt)
            key = nxt
        else:
            if origin_of_host.get(key) not in (None, key):
                raise SourceAdmissionError(
                    "SYNDICATION_METADATA_INVALID",
                    "syndication chain exceeds the supported depth.",
                )
        resolved[retrieval_id] = key
    return resolved


def classify_source(descriptor: SourceDescriptor) -> SourceClass | None:
    """Return the effective class, or ``None`` when it cannot be established.

    An orientation host caps the class; it never raises one.  ``None`` means
    fail-closed: the corpus needs an explicit classification for this source.
    """
    if descriptor.host in ORIENTATION_HOSTS:
        return SourceClass.ORIENTATION
    return descriptor.source_class


def is_time_sensitive(claims: Iterable[str], *, markers: Sequence[str] | None = None) -> bool:
    """Deterministic, conservative detection of claims that decay with time."""
    vocabulary = tuple(markers) if markers is not None else (
        "current", "currently", "today", "this year", "latest", "recent",
        "recently", "now", "as of", "so far this", "record high",
        "record low", "year to date", "ytd", "just announced", "upcoming",
    )
    for claim in claims:
        if not isinstance(claim, str):
            continue
        lowered = claim.lower()
        if any(marker in lowered for marker in vocabulary):
            return True
    return False


def evaluate_source_admission(
    descriptors: Sequence[SourceDescriptor],
    *,
    confirmed_claims: Sequence[str],
    policy: SourceAdmissionPolicy | None = None,
    time_sensitive: bool | None = None,
    now: datetime | None = None,
    claim_markers: Sequence[str] | None = None,
) -> SourceAdmissionOutcome:
    """Decide whether this corpus may support an ARTICLE, and say why not."""
    active = policy or SourceAdmissionPolicy()
    reasons: list[str] = []
    findings: list[dict[str, object]] = []

    if not confirmed_claims:
        return SourceAdmissionOutcome(
            admitted=False,
            reasons=(CLAIM_WITHOUT_ADMITTED_EVIDENCE,),
            findings=({"code": CLAIM_WITHOUT_ADMITTED_EVIDENCE,
                       "detail": "corpus carries no confirmed claim"},),
            policy_fingerprint=active.fingerprint(),
        )

    # 0. Independence keys, with syndication canonicalized the same way as any
    #    other URL and chains collapsed onto their ultimate origin.
    try:
        independence = resolve_independence_keys(descriptors)
    except SourceAdmissionError as exc:
        return SourceAdmissionOutcome(
            admitted=False,
            reasons=(SYNDICATION_METADATA_INVALID,),
            findings=({"code": SYNDICATION_METADATA_INVALID,
                       "detail": str(exc)},),
            policy_fingerprint=active.fingerprint(),
        )

    # 1. Classification. An unknown class is never guessed.
    classified: list[tuple[SourceDescriptor, SourceClass]] = []
    for descriptor in descriptors:
        effective = classify_source(descriptor)
        if effective is None:
            reasons.append(SOURCE_CLASSIFICATION_UNKNOWN)
            findings.append({
                "code": SOURCE_CLASSIFICATION_UNKNOWN,
                "url": descriptor.url,
                "retrieval_id": descriptor.retrieval_id,
            })
            continue
        classified.append((descriptor, effective))

    # 2. Deduplicate qualitatively equivalent material.  Identical canonical
    #    text, or a declared syndication parent, collapses to one source.
    admitted: list[AdmittedSource] = []
    seen_content: dict[str, str] = {}
    seen_retrievals: set[int] = set()
    for descriptor, effective in classified:
        if descriptor.retrieval_id in seen_retrievals:
            findings.append({
                "code": SYNDICATED_DUPLICATE_SOURCES,
                "url": descriptor.url,
                "detail": "repeated retrieval identity",
            })
            reasons.append(SYNDICATED_DUPLICATE_SOURCES)
            continue
        digest = descriptor.content_sha256
        if digest and digest in seen_content:
            findings.append({
                "code": SYNDICATED_DUPLICATE_SOURCES,
                "url": descriptor.url,
                "duplicate_of": seen_content[digest],
                "detail": "identical canonical text",
            })
            reasons.append(SYNDICATED_DUPLICATE_SOURCES)
            continue
        if digest:
            seen_content[digest] = descriptor.url
        seen_retrievals.add(descriptor.retrieval_id)
        admitted.append(
            AdmittedSource(
                url=descriptor.url,
                retrieval_id=descriptor.retrieval_id,
                source_class=effective,
                independence_key=independence[descriptor.retrieval_id],
            )
        )

    # 3. A declared syndication parent must not also be counted separately.
    owners = {item.independence_key for item in admitted}
    if len(admitted) < active.min_admitted_sources:
        reasons.append(TOO_FEW_ADMITTED_SOURCES)
        findings.append({
            "code": TOO_FEW_ADMITTED_SOURCES,
            "admitted": len(admitted),
            "required": active.min_admitted_sources,
        })
    if len(owners) < active.min_independent_owners:
        reasons.append(INSUFFICIENT_SOURCE_INDEPENDENCE)
        findings.append({
            "code": INSUFFICIENT_SOURCE_INDEPENDENCE,
            "independent_owners": len(owners),
            "required": active.min_independent_owners,
        })

    # 4. Orientation material never substitutes for independent evidence.
    non_orientation = [
        item for item in admitted if item.source_class is not SourceClass.ORIENTATION
    ]
    if admitted and not non_orientation:
        reasons.append(ORIENTATION_ONLY_CORPUS)
        findings.append({
            "code": ORIENTATION_ONLY_CORPUS,
            "detail": "every admitted source is encyclopaedic/aggregated",
        })
    elif admitted:
        orientation_share = 1.0 - (len(non_orientation) / len(admitted))
        if orientation_share > active.max_orientation_share:
            reasons.append(ORIENTATION_ONLY_CORPUS)
            findings.append({
                "code": ORIENTATION_ONLY_CORPUS,
                "orientation_share": round(orientation_share, 4),
                "max_allowed": active.max_orientation_share,
            })

    # 5. Prefer, and where available require, an originating record.
    if active.require_primary_source and not any(
        item.source_class is SourceClass.PRIMARY for item in admitted
    ):
        reasons.append(NO_PRIMARY_SOURCE)
        findings.append({
            "code": NO_PRIMARY_SOURCE,
            "detail": "no admitted source is an originating record",
        })

    # 6. Freshness only where the topic actually decays.
    sensitive = (
        is_time_sensitive(confirmed_claims, markers=claim_markers)
        if time_sensitive is None else bool(time_sensitive)
    )
    if sensitive:
        reference = now or datetime.now(timezone.utc)
        fresh = 0
        dated = 0
        for descriptor, _ in classified:
            published = descriptor.published_at
            if published is None:
                continue
            dated += 1
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            age_days = (reference - published).days
            if 0 <= age_days <= active.freshness_max_age_days:
                fresh += 1
        # "No source carries a date" is not the same finding as "every dated
        # source is too old", and conflating them made this gate unpassable:
        # discovery never recorded publication dates at all, so every
        # time-sensitive topic was scored stale on missing metadata rather than
        # on age.  An undated corpus is recorded as unverifiable and left to the
        # reviewer; a genuinely old one still blocks.
        if dated == 0:
            findings.append({
                "code": FRESHNESS_UNVERIFIABLE,
                "max_age_days": active.freshness_max_age_days,
                "detail": "no admitted source reports a publication date",
            })
        elif fresh < 1:
            reasons.append(STALE_TIME_SENSITIVE_CORPUS)
            findings.append({
                "code": STALE_TIME_SENSITIVE_CORPUS,
                "max_age_days": active.freshness_max_age_days,
                "dated_sources": dated,
                "detail": "time-sensitive claims need at least one fresh source",
            })

    # 7. Every confirmed claim must be reachable from admitted evidence.
    admitted_urls = {item.url for item in admitted}
    supported = {
        descriptor.supports_claim
        for descriptor, _ in classified
        if descriptor.supports_claim and descriptor.url in admitted_urls
    }
    uncovered = [claim for claim in confirmed_claims if claim not in supported]
    if uncovered:
        reasons.append(CLAIM_WITHOUT_ADMITTED_EVIDENCE)
        findings.append({
            "code": CLAIM_WITHOUT_ADMITTED_EVIDENCE,
            "uncovered_claims": len(uncovered),
        })

    ordered: dict[str, None] = {}
    deduped = tuple(
        reason for reason in reasons
        if not (reason in ordered or ordered.setdefault(reason, None))
    )
    return SourceAdmissionOutcome(
        admitted=not deduped,
        reasons=deduped,
        findings=tuple(findings),
        admitted_sources=tuple(admitted),
        independent_owner_count=len(owners),
        policy_fingerprint=active.fingerprint(),
    )


# A card source carries an operator/extractor classification in source_type.
# OTHER is deliberately absent: an unclassified source fails closed rather
# than being guessed into a supporting role.
SOURCE_TYPE_TO_CLASS: dict[str, SourceClass] = {
    "PRIMARY": SourceClass.PRIMARY,
    "DATA": SourceClass.PRIMARY,
    "SECONDARY": SourceClass.SUPPORTING,
}


def descriptors_from_research_card(
    sources: Iterable[object],
    *,
    retrieval_ids_by_url: Mapping[str, int],
    canonical_sha256_by_url: Mapping[str, str] | None = None,
    published_at_by_url: Mapping[str, datetime] | None = None,
) -> tuple[SourceDescriptor, ...]:
    """Descriptors for the authoritative runtime gate, from persisted rows only.

    Nothing here is inferred from model prose: the class comes from the stored
    ``source_type`` classification, the identity from the approved retrieval,
    and the duplicate signal from the canonical text hash the E1 recorder
    computed.  A source without an approved retrieval is not silently dropped —
    it is described with a sentinel so admission counts it as unclassified.
    """
    digests = dict(canonical_sha256_by_url or {})
    published = dict(published_at_by_url or {})
    descriptors: list[SourceDescriptor] = []
    for index, source in enumerate(sources):
        url = getattr(source, "url", None)
        if not isinstance(url, str) or not url.strip():
            raise SourceAdmissionError(
                "SOURCE_URL_INVALID", "Card source must carry a URL.",
            )
        source_type = getattr(source, "source_type", None)
        raw_type = getattr(source_type, "value", source_type)
        descriptors.append(
            SourceDescriptor(
                url=url,
                retrieval_id=int(retrieval_ids_by_url.get(url, -(index + 1))),
                source_class=SOURCE_TYPE_TO_CLASS.get(str(raw_type)),
                published_at=published.get(url),
                content_sha256=digests.get(url),
                supports_claim=getattr(source, "supports_claim", None),
            )
        )
    return tuple(descriptors)


def descriptors_from_card_sources(
    sources: Iterable[object],
    retrieval_ids_by_url: Mapping[str, int],
    *,
    classifications: Mapping[str, SourceClass] | None = None,
    published_at_by_url: Mapping[str, datetime] | None = None,
    content_sha256_by_url: Mapping[str, str] | None = None,
    syndication_by_url: Mapping[str, str] | None = None,
) -> tuple[SourceDescriptor, ...]:
    """Build descriptors from persisted card sources plus explicit metadata.

    Nothing is inferred from the source record itself beyond its URL and the
    claim it was recorded against; every other input is supplied explicitly by
    the caller from persisted or operator-provided data.
    """
    classes = dict(classifications or {})
    published = dict(published_at_by_url or {})
    digests = dict(content_sha256_by_url or {})
    syndication = dict(syndication_by_url or {})
    descriptors: list[SourceDescriptor] = []
    for source in sources:
        url = getattr(source, "url", None)
        if not isinstance(url, str) or not url.strip():
            raise SourceAdmissionError(
                "SOURCE_URL_INVALID", "Card source must carry a URL.",
            )
        retrieval_id = retrieval_ids_by_url.get(url)
        if retrieval_id is None:
            raise SourceAdmissionError(
                "SOURCE_RETRIEVAL_UNKNOWN",
                f"Source {url} has no approved retrieval identity.",
            )
        descriptors.append(
            SourceDescriptor(
                url=url,
                retrieval_id=int(retrieval_id),
                source_class=classes.get(url),
                published_at=published.get(url),
                content_sha256=digests.get(url),
                syndication_of=syndication.get(url),
                supports_claim=getattr(source, "supports_claim", None),
            )
        )
    return tuple(descriptors)
