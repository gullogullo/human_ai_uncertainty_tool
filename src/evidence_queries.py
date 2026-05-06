"""Direct evidence interrogation before uncertainty computation."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from src.fields import normalize_field_value
from src.models import EvidenceAnswer, Record

_BUILDER_PATTERNS = [
    r"\bmade by ([A-Z][A-Za-z .'-]+)",
    r"\bbuilt by ([A-Z][A-Za-z .'-]+)",
    r"\bmaker[: ]+([A-Z][A-Za-z .'-]+)",
    r"\bbuilder[: ]+([A-Z][A-Za-z .'-]+)",
]


def _normalize_scalar(value: Any) -> str:
    """Normalize possibly mixed scalar/list values into a safe string."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " | ".join(str(v).strip() for v in value if v is not None and str(v).strip())
    if isinstance(value, dict):
        return str(value)
    return str(value).strip()


def _base_item(record: Record) -> Dict[str, str]:
    return {
        "record_key": str(record.key),
        "source": str(record.source or ""),
        "title": str(record.title or ""),
        "source_url": _normalize_scalar(record.source_url),
    }


def list_records_with_images(records: List[Record]) -> EvidenceAnswer:
    items = []
    for record in records:
        if record.image_url:
            item = _base_item(record)
            item["image_url"] = _normalize_scalar(record.image_url)
            items.append(item)

    return EvidenceAnswer(
        question_id="records_with_images",
        label="Records with images",
        items=items,
        notes=["This is direct evidence from retrieved records; no uncertainty computation is needed."],
    )


def list_candidate_builders(records: List[Record]) -> EvidenceAnswer:
    items = []
    notes = []

    for record in records:
        builder = (
            record.metadata.get("artist")
            or record.metadata.get("creator")
            or record.metadata.get("maker")
            or record.metadata.get("builder")
        )

        if builder:
            item = _base_item(record)
            item["builder"] = normalize_field_value(builder)
            item["evidence_type"] = "structured_field"
            item["evidence_span"] = ""
            items.append(item)
            continue

        description = normalize_field_value(record.metadata.get("description"))
        if description:
            for pattern in _BUILDER_PATTERNS:
                match = re.search(pattern, description)
                if match:
                    item = _base_item(record)
                    item["builder"] = match.group(1).strip()
                    item["evidence_type"] = "description_candidate"
                    item["evidence_span"] = match.group(0)
                    items.append(item)
                    break

    if any(i.get("evidence_type") == "description_candidate" for i in items):
        notes.append("Some builders come only from description patterns and require human validation.")

    return EvidenceAnswer(
        question_id="candidate_builders",
        label="Candidate builders",
        items=items,
        notes=notes,
    )


def list_date_expressions(records: List[Record]) -> EvidenceAnswer:
    items = []
    for record in records:
        value = (
            record.metadata.get("date")
            or record.metadata.get("date_created")
            or record.metadata.get("dating")
        )
        if value:
            item = _base_item(record)
            item["date_expression"] = normalize_field_value(value)
            items.append(item)

    return EvidenceAnswer(
        question_id="date_expressions",
        label="Date expressions",
        items=items,
        notes=["This collects source-native date expressions without harmonizing them."],
    )


def list_material_mentions(records: List[Record]) -> EvidenceAnswer:
    items = []
    for record in records:
        value = (
            record.metadata.get("medium")
            or record.metadata.get("material")
            or record.metadata.get("materials")
        )
        if value:
            item = _base_item(record)
            item["material"] = normalize_field_value(value)
            item["evidence_type"] = "structured_field"
            items.append(item)

    return EvidenceAnswer(
        question_id="materials",
        label="Material mentions",
        items=items,
        notes=[],
    )


def run_standard_evidence_queries(records: List[Record]) -> Dict[str, EvidenceAnswer]:
    return {
        "records_with_images": list_records_with_images(records),
        "candidate_builders": list_candidate_builders(records),
        "date_expressions": list_date_expressions(records),
        "materials": list_material_mentions(records),
    }
