"""VCITE data model (spec §4) — Python dataclasses."""

from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime
import json

from .hash import compute_hash

VALID_RELATIONS = {
    "supports",
    "contradicts",
    "defines",
    "quantifies",
    "contextualizes",
    "method",
    "cautions",
}

JSONLD_CONTEXT = "https://vcite.pub/ns/v1/"


@dataclass
class VCiteSource:
    """Bibliographic source metadata (spec §4.2)."""

    title: str
    authors: list[str] = field(default_factory=list)
    year: Optional[int] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    archive_url: Optional[str] = None
    venue: Optional[str] = None
    source_type: Optional[str] = None  # academic, journalism, web, grey, ai_output


@dataclass
class VCiteTarget:
    """Passage location and verification data (spec §4.3)."""

    text_exact: str
    hash: str = ""  # computed automatically if empty
    text_before: str = ""
    text_after: str = ""
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    page_ref: Optional[str] = None
    section: Optional[str] = None
    fragment_url: Optional[str] = None

    def __post_init__(self):
        if not self.hash:
            self.hash = compute_hash(
                self.text_exact, self.text_before, self.text_after
            )


@dataclass
class VCiteCitation:
    """A single VCITE citation object (spec §4.1)."""

    vcite: str  # spec version, e.g., "1.0"
    id: str
    source: VCiteSource
    target: VCiteTarget
    relation: str
    captured_at: str  # ISO 8601
    captured_by: str  # "author" or "model"
    enrichment: Optional[dict] = None

    def __post_init__(self):
        if self.relation not in VALID_RELATIONS and not self.relation.startswith(
            "x-"
        ):
            raise ValueError(f"Invalid relation: {self.relation}")
        if self.captured_by not in ("author", "model"):
            raise ValueError(
                f"captured_by must be 'author' or 'model', got: {self.captured_by}"
            )

    def to_dict(self) -> dict:
        """Serialize to plain dict (JSON-ready), stripping None values."""
        d = asdict(self)
        return _strip_none(d)

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_jsonld(self) -> dict:
        """Serialize to JSON-LD with @context and @type."""
        d = self.to_dict()
        d["@context"] = JSONLD_CONTEXT
        d["@type"] = "VCiteCitation"
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "VCiteCitation":
        """Deserialize from dict."""
        source_data = data["source"]
        source = VCiteSource(**source_data)

        target_data = data["target"]
        target = VCiteTarget(**target_data)

        return cls(
            vcite=data["vcite"],
            id=data["id"],
            source=source,
            target=target,
            relation=data["relation"],
            captured_at=data["captured_at"],
            captured_by=data["captured_by"],
            enrichment=data.get("enrichment"),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "VCiteCitation":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))

    def verify(self) -> bool:
        """Verify the hash matches the target text."""
        expected = compute_hash(
            self.target.text_exact,
            self.target.text_before,
            self.target.text_after,
        )
        return self.target.hash == expected

    @property
    def conformance_level(self) -> int:
        """Return conformance level (1, 2, or 3).

        L1: text_exact + hash (minimal)
        L2: L1 + text_before + text_after + source URL/DOI (standard)
        L3: L2 + archive_url + fragment_url (enhanced)
        """
        # L3 requires archive_url and fragment_url
        has_l3 = bool(self.source.archive_url) and bool(self.target.fragment_url)
        # L2 requires context windows and a retrievable source
        has_context = bool(self.target.text_before) or bool(self.target.text_after)
        has_source_url = bool(self.source.doi) or bool(self.source.url)
        has_l2 = has_context and has_source_url

        if has_l2 and has_l3:
            return 3
        if has_l2:
            return 2
        return 1


def _strip_none(obj):
    """Recursively remove keys with None values from a dict."""
    if isinstance(obj, dict):
        return {k: _strip_none(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_strip_none(item) for item in obj]
    return obj
