"""Field classification, normalization, and validated alignment helpers."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Set

HIDDEN_ANALYSIS_FIELDS = {"claims_keys", "match_reason", "retrieval_class"}
DESCRIPTION_FIELDS = {"description"}
IMAGE_RELEVANT_FIELDS = {"title", "object_name", "description", "present_type", "present_type_candidate", "material", "materials"}

FIELD_FAMILY_RULES = {
    "maker": {"artist", "creator", "maker", "builder", "author", "principalmaker"},
    "date_expression": {"date", "objectDate", "issued", "date_created", "dating", "datecreated"},
    "present_type": {"object_name", "objectName", "title", "type", "object_type", "artform", "objecttype"},
    "material": {"medium", "material", "materials", "samplematerial", "_samplematerial"},
    "subject": {"subject", "topic", "keywords"},
    "description": {"description"},
}

def normalize_field_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple, set)):
        return " | ".join(str(v).strip() for v in value if v is not None and str(v).strip())
    if isinstance(value, dict):
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            return str(value).strip()
    return str(value).strip()

def get_non_empty_values(values_dict: Dict[str, Any]) -> Dict[str, str]:
    return {k: normalize_field_value(v) for k, v in values_dict.items() if normalize_field_value(v)}

def make_arrow_safe(value: Any) -> Any:
    return "—" if normalize_field_value(value) == "" else normalize_field_value(value)

def make_comparison_table_arrow_safe(table: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {field: {k: make_arrow_safe(v) for k, v in row.items()} for field, row in table.items()}

def get_visible_analysis_fields(records: List[Any]) -> List[str]:
    fields: Set[str] = set()
    for record in records:
        fields.update(record.metadata.keys())
    return [f for f in sorted(fields) if f not in HIDDEN_ANALYSIS_FIELDS]

def infer_field_family(field_name: str) -> str:
    lower = (field_name or "").lower()
    for family, names in FIELD_FAMILY_RULES.items():
        if lower in {n.lower() for n in names}:
            return family
    return "other"

def default_validated_mappings(records: List[Any]) -> List[dict]:
    found = {}
    for record in records:
        for field in record.metadata.keys():
            if field in HIDDEN_ANALYSIS_FIELDS:
                continue
            family = infer_field_family(field)
            if family == "other":
                continue
            found.setdefault(family, set()).add(field)

    mappings = []
    for family, source_fields in sorted(found.items()):
        claim_type = family
        mappings.append(
            {
                "field_family": family,
                "source_fields": sorted(source_fields),
                "claim_type": claim_type,
                "approved": True,
                "notes": "Auto-proposed; review in the UI.",
            }
        )
    return mappings

def tokenize(text: str) -> List[str]:
    return [t for t in re.split(r"[\W_]+", (text or "").lower()) if len(t) > 2]
