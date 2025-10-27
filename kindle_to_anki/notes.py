"""
Utilities for building deterministic Notes strings from Gemini metadata.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

GENERIC_DOMAIN_TOKENS: Sequence[str] = (
    "general",
    "generic",
    "allgemein",
    "neutral",
    "none",
    "standard",
)

NEUTRAL_REGISTERS: Sequence[str] = (
    "neutral",
    "standard",
    "normal",
    "allgemein",
    "formell-neutral",
)


def _to_string(value: Any) -> str:
    """Return a trimmed string representation or an empty string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.strip().split())
    if isinstance(value, (int, float)):
        return str(value)
    return " ".join(str(value).strip().split())


def _dedupe_preserve_order(items: Iterable[str]) -> List[str]:
    """Return a list with duplicates removed while preserving order."""
    seen = set()
    result: List[str] = []
    for item in items:
        lowered = item.lower()
        if lowered and lowered not in seen:
            seen.add(lowered)
            result.append(item)
    return result


def extract_notes_metadata(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and normalize metadata fields that control Notes generation.

    Args:
        raw: Gemini response dictionary for a single word.

    Returns:
        Dict containing sanitized metadata signals.
    """
    if not isinstance(raw, dict):
        return {}

    lowered: Dict[str, Any] = {}
    for key, value in raw.items():
        if isinstance(key, str):
            lowered[key.lower()] = value

    def _get(*keys: str) -> Any:
        for key in keys:
            if key in lowered:
                return lowered[key]
        return None

    metadata: Dict[str, Any] = {}

    notes_value = _to_string(_get("notes", "note"))
    if notes_value:
        metadata["notes"] = notes_value

    ambiguity_value = _to_string(_get("ambiguity", "ambiguity_level"))
    if ambiguity_value:
        metadata["ambiguity"] = ambiguity_value.lower()

    sense_value = _to_string(_get("sense", "meaning"))
    if sense_value:
        metadata["sense"] = sense_value

    domain_value = _to_string(_get("domain", "field", "fachgebiet"))
    if domain_value:
        metadata["domain"] = domain_value

    register_value = _to_string(_get("register", "style"))
    if register_value:
        metadata["register"] = register_value

    alternatives_value = _get("alternatives", "alternate_translations", "varianten")
    alternatives: List[str] = []
    if isinstance(alternatives_value, str):
        alternatives = [item.strip() for item in alternatives_value.split(",")]
    elif isinstance(alternatives_value, (list, tuple)):
        alternatives = [str(item).strip() for item in alternatives_value]

    alternatives = _dedupe_preserve_order(
        item for item in alternatives if _to_string(item)
    )
    if alternatives:
        metadata["alternatives"] = alternatives[:3]

    false_friend_value = _get("false_friend", "falsefriend", "falsefriend_hint")
    if isinstance(false_friend_value, bool):
        if false_friend_value:
            metadata["false_friend"] = True
    else:
        false_friend_str = _to_string(false_friend_value)
        if false_friend_str:
            metadata["false_friend"] = false_friend_str

    collocations_value = _get("collocations", "kollokationen")
    collocations: List[str] = []
    if isinstance(collocations_value, str):
        collocations = [collocations_value]
    elif isinstance(collocations_value, (list, tuple)):
        collocations = [str(item).strip() for item in collocations_value]

    collocations = _dedupe_preserve_order(
        _to_string(item) for item in collocations if _to_string(item)
    )
    if collocations:
        metadata["collocations"] = collocations[:2]

    anchor_value = _to_string(_get("anchor"))
    if anchor_value:
        metadata["anchor"] = anchor_value

    confidence_value = _get("confidence")
    if isinstance(confidence_value, (int, float)):
        metadata["confidence"] = float(confidence_value)
    else:
        try:
            confidence_parsed = float(str(confidence_value).strip())
            if confidence_parsed == confidence_parsed:  # exclude NaN
                metadata["confidence"] = confidence_parsed
        except (ValueError, TypeError):
            pass

    return metadata


def build_notes_line(
    metadata: Dict[str, Any], *, separator: str = " · ", max_length: int = 300
) -> str:
    """
    Deterministically build a concise Notes string from metadata signals.

    The order and inclusion criteria follow the product specification:
      1. false_friend
      2. notes
      3. sense (only when ambiguity medium/high)
      4. domain (non-generic only)
      5. register (non-neutral only)
      6. alternatives (max. 3, deduped)
      7. single collocation
      8. Soft cap at ~300 characters (last items skipped if limit exceeded)
    """
    if not metadata:
        return ""

    components: List[str] = []

    def try_add(fragment: Optional[str]) -> None:
        fragment = _to_string(fragment)
        if not fragment:
            return
        projection = separator.join((*components, fragment)) if components else fragment
        if len(projection) <= max_length:
            components.append(fragment)

    false_friend = metadata.get("false_friend")
    if isinstance(false_friend, str):
        try_add(f"False Friend: {false_friend}")
    elif isinstance(false_friend, bool) and false_friend:
        try_add("False Friend beachten")

    try_add(metadata.get("notes"))

    ambiguity = _to_string(metadata.get("ambiguity")).lower()
    if ambiguity in {"medium", "hoch", "high"}:
        sense = metadata.get("sense")
        if sense:
            try_add(f"Sinn: {_to_string(sense)}")

    domain = _to_string(metadata.get("domain"))
    if domain and domain.lower() not in GENERIC_DOMAIN_TOKENS:
        try_add(domain)

    register = _to_string(metadata.get("register"))
    if register and register.lower() not in NEUTRAL_REGISTERS:
        try_add(f"Register: {register}")

    alternatives = metadata.get("alternatives") or []
    if isinstance(alternatives, (list, tuple)):
        formatted = ", ".join(_dedupe_preserve_order(_to_string(item) for item in alternatives if _to_string(item)))
        if formatted:
            try_add(f"Alternativen: {formatted}")

    collocations = metadata.get("collocations") or []
    if isinstance(collocations, (list, tuple)):
        for collocation in collocations:
            try_add(_to_string(collocation))
            break

    return separator.join(components)


__all__ = ["build_notes_line", "extract_notes_metadata"]
