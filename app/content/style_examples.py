"""Auditable ARTICLE style examples derived from the private reference corpus.

The private corpus is never sent to a model.  This module selects a small,
fixed set of short paragraphs by *rhetorical function*, binds each one to a
durable example ID, and exposes only those fragments plus their hashes.  The
raw file is opened read-only, is never written, moved or committed, and its
full text never leaves this process.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from pathlib import Path
from typing import Any

from app.content.foundation import canonical_json, sha256_text


STYLE_EXAMPLE_SET_VERSION = "article_style_examples_v1"
STYLE_CORPUS_ID = "article_style_samples_v1"
STYLE_CORPUS_RELATIVE_PATH = (
    "data/style-references/articles/article_style_samples_v1.txt"
)

# The owner-approved corpus baseline.  A different corpus is not silently
# accepted: the loader fails closed rather than teaching the writer an
# unreviewed voice.
STYLE_CORPUS_SHA256 = (
    "0b05cefa6701e6447c44810b686828a83c19ca7ffb29066778a13c24207acb1d"
)
STYLE_CORPUS_BYTES = 57561

# A style example illustrates a move, not a phrase to reuse.  Anything long
# enough to be lifted wholesale is rejected before it can reach a prompt.
MIN_EXAMPLE_CHARS = 150
MAX_EXAMPLE_CHARS = 900
MIN_EXAMPLES = 3
MAX_EXAMPLES = 5


class StyleExampleError(RuntimeError):
    """The style corpus or the requested example selection is unusable."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


class RhetoricalFunction(str, Enum):
    """The five functions a selected paragraph is allowed to illustrate."""

    OPENING = "OPENING"
    CONCRETE_TO_SYSTEM = "CONCRETE_TO_SYSTEM"
    MECHANISM = "MECHANISM"
    COUNTERARGUMENT = "COUNTERARGUMENT"
    ENDING = "ENDING"


# Reviewed selection: one paragraph per rhetorical function.  Both the ordinal
# and the fragment hash are pinned, so a corpus edit that shifts or rewrites a
# paragraph fails closed instead of silently changing the writer's examples.
APPROVED_ARTICLE_EXAMPLES: tuple[tuple[RhetoricalFunction, int, str], ...] = (
    (RhetoricalFunction.OPENING, 65, "974f069d90"),
    (RhetoricalFunction.CONCRETE_TO_SYSTEM, 45, "256abfccb2"),
    (RhetoricalFunction.MECHANISM, 60, "39432e9c97"),
    (RhetoricalFunction.COUNTERARGUMENT, 70, "a139cf852d"),
    (RhetoricalFunction.ENDING, 76, "17d1efd98e"),
)


@dataclass(frozen=True)
class StyleExample:
    """One short fragment plus everything needed to audit it later."""

    example_id: str
    rhetorical_function: RhetoricalFunction
    ordinal: int
    text: str
    text_sha256: str
    chars: int

    def prompt_payload(self) -> dict[str, Any]:
        """Exactly what a model may see: the function and the fragment."""
        return {
            "example_id": self.example_id,
            "rhetorical_function": self.rhetorical_function.value,
            "text": self.text,
        }

    def audit_payload(self) -> dict[str, Any]:
        return {
            "example_id": self.example_id,
            "rhetorical_function": self.rhetorical_function.value,
            "ordinal": self.ordinal,
            "text_sha256": self.text_sha256,
            "chars": self.chars,
        }


@dataclass(frozen=True)
class StyleExampleSet:
    """A durable, hash-addressed selection bound to one corpus version."""

    schema_version: str
    corpus_id: str
    corpus_sha256: str
    corpus_bytes: int
    paragraph_count: int
    examples: tuple[StyleExample, ...]

    @property
    def example_ids(self) -> tuple[str, ...]:
        return tuple(example.example_id for example in self.examples)

    def prompt_payload(self) -> list[dict[str, Any]]:
        return [example.prompt_payload() for example in self.examples]

    def audit_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "corpus_id": self.corpus_id,
            "corpus_sha256": self.corpus_sha256,
            "corpus_bytes": self.corpus_bytes,
            "paragraph_count": self.paragraph_count,
            "examples": [example.audit_payload() for example in self.examples],
        }

    def fingerprint(self) -> str:
        return sha256_text(canonical_json(self.audit_payload()))


def _repository_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def default_style_corpus_path(project_root: Path) -> Path:
    """Prefer the operator's project root; fall back to the shipped asset.

    The corpus is a versioned repository asset like the style profiles, so a
    project root that does not carry its own copy still resolves to the exact
    approved bytes rather than silently writing without examples.
    """
    candidate = project_root / STYLE_CORPUS_RELATIVE_PATH
    if candidate.exists():
        return candidate
    return _repository_root() / STYLE_CORPUS_RELATIVE_PATH


def example_id(ordinal: int, text: str) -> str:
    """Stable identity of one corpus paragraph: position plus content hash."""
    return f"ASV1-P{ordinal:03d}-{sha256_text(text)[:10]}"


def split_corpus_paragraphs(raw: bytes) -> tuple[str, ...]:
    """Deterministic paragraph split; line-ending style must not change IDs."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StyleExampleError(
            "STYLE_CORPUS_NOT_UTF8", "Style corpus must be UTF-8 text.",
        ) from exc
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = [block.strip() for block in normalized.split("\n\n")]
    return tuple(block for block in blocks if block)


def load_article_style_examples(
    corpus_path: Path,
    *,
    expected_sha256: str = STYLE_CORPUS_SHA256,
    expected_bytes: int = STYLE_CORPUS_BYTES,
    selection: tuple[tuple[RhetoricalFunction, int, str], ...] = (
        APPROVED_ARTICLE_EXAMPLES
    ),
) -> StyleExampleSet:
    """Read the corpus read-only and return only the approved fragments."""
    if not MIN_EXAMPLES <= len(selection) <= MAX_EXAMPLES:
        raise StyleExampleError(
            "STYLE_EXAMPLE_COUNT_INVALID",
            f"ARTICLE requires between {MIN_EXAMPLES} and {MAX_EXAMPLES} examples.",
        )
    functions = [function for function, _, _ in selection]
    if len(set(functions)) != len(functions):
        raise StyleExampleError(
            "STYLE_EXAMPLE_FUNCTION_DUPLICATE",
            "Each rhetorical function may appear at most once.",
        )
    try:
        raw = corpus_path.read_bytes()
    except OSError as exc:
        raise StyleExampleError(
            "STYLE_CORPUS_UNREADABLE", "Style corpus could not be read.",
        ) from exc
    corpus_sha256 = _sha256_bytes(raw)
    if len(raw) != expected_bytes or corpus_sha256 != expected_sha256:
        raise StyleExampleError(
            "STYLE_CORPUS_UNAPPROVED",
            "Style corpus bytes do not match the approved reviewed baseline.",
        )
    paragraphs = split_corpus_paragraphs(raw)

    examples: list[StyleExample] = []
    for function, ordinal, expected_prefix in selection:
        if ordinal < 0 or ordinal >= len(paragraphs):
            raise StyleExampleError(
                "STYLE_EXAMPLE_ORDINAL_OUT_OF_RANGE",
                f"Paragraph #{ordinal} does not exist in the approved corpus.",
            )
        text = paragraphs[ordinal]
        identifier = example_id(ordinal, text)
        if not identifier.endswith(expected_prefix):
            raise StyleExampleError(
                "STYLE_EXAMPLE_CONTENT_DRIFTED",
                f"Paragraph #{ordinal} no longer matches its reviewed fragment hash.",
            )
        if not MIN_EXAMPLE_CHARS <= len(text) <= MAX_EXAMPLE_CHARS:
            raise StyleExampleError(
                "STYLE_EXAMPLE_LENGTH_INVALID",
                f"Example {identifier} is outside the reviewed short-fragment range.",
            )
        examples.append(
            StyleExample(
                example_id=identifier,
                rhetorical_function=function,
                ordinal=ordinal,
                text=text,
                text_sha256=sha256_text(text),
                chars=len(text),
            )
        )
    return StyleExampleSet(
        schema_version=STYLE_EXAMPLE_SET_VERSION,
        corpus_id=STYLE_CORPUS_ID,
        corpus_sha256=corpus_sha256,
        corpus_bytes=len(raw),
        paragraph_count=len(paragraphs),
        examples=tuple(examples),
    )


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()
