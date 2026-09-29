"""Validated, exact-match metadata constraints for RAG retrieval.

The accepted vocabulary is deliberately small.  Callers must supply metadata
explicitly; this module never infers labels from filenames or document text.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


SUPPORTED_METADATA_VALUES: dict[str, frozenset[str]] = {
    "subject": frozenset({"chinese", "english", "math"}),
    "language_form": frozenset({"vernacular", "classical"}),
    "genre": frozenset({"informational", "argumentative", "narrative"}),
}


@dataclass(frozen=True)
class MetadataConstraintDecision:
    status: str
    reason: str
    requested: dict[str, Any]
    constraints: dict[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "requested": self.requested,
            "constraints": self.constraints,
        }


def normalize_metadata_constraints(value: Any) -> MetadataConstraintDecision:
    """Validate the supported constraint vocabulary without fuzzy matching."""
    if value is None or value == {}:
        return MetadataConstraintDecision("not_requested", "no_constraints", {}, {})
    if not isinstance(value, Mapping):
        return MetadataConstraintDecision(
            "not_applied", "constraints_not_mapping", {}, {}
        )

    requested = {str(key): item for key, item in sorted(value.items(), key=lambda row: str(row[0]))}
    for key, item in requested.items():
        if key not in SUPPORTED_METADATA_VALUES:
            return MetadataConstraintDecision(
                "not_applied", f"unsupported_key:{key}", requested, {}
            )
        if not isinstance(item, str) or item not in SUPPORTED_METADATA_VALUES[key]:
            return MetadataConstraintDecision(
                "not_applied", f"unsupported_value:{key}", requested, {}
            )

    return MetadataConstraintDecision(
        "eligible",
        "supported_exact_match",
        requested,
        {key: requested[key] for key in sorted(requested)},
    )


def validate_ingest_metadata(value: Any) -> dict[str, str]:
    """Validate explicitly supplied per-document retrieval metadata."""
    decision = normalize_metadata_constraints(value)
    if decision.status != "eligible":
        raise ValueError(decision.reason)
    return decision.constraints
