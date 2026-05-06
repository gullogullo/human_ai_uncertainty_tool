"""Alignment helpers for graph-selected record subsets.

This module supports two comparison layers:

1. Native/source comparison
   - field union table built directly from record metadata

2. Interpreted comparison
   - claim-type-based table built from ExtractedClaim objects
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Iterable

from src.models import Record, ExtractedClaim
from src.fields import normalize_field_value

logger = logging.getLogger(__name__)


# -----------------------------
# Comparable record selection
# -----------------------------

def get_comparable_records(records: List[Record]) -> List[Record]:
    """
    Exclude future semantic anchors from first-class record comparison.
    """
    comparable = [r for r in records if not r.is_semantic_anchor]
    logger.info("Comparable records: %d out of %d selected", len(comparable), len(records))
    return comparable


# -----------------------------
# Native/source comparison
# -----------------------------

def extract_all_fields(records: List[Record]) -> List[str]:
    """
    Union of native source fields across selected comparable records.
    """
    all_fields = set()
    for record in records:
        all_fields.update(record.metadata.keys())
    return sorted(all_fields)


def build_comparison_table(records: List[Record]) -> Dict[str, Dict[str, Any]]:
    """
    Build a native/source field comparison table.

    Output shape:
        {
            "title": {
                "the_met:123": "Claviorganum",
                "europeana:abc": "Harpsichord",
            },
            ...
        }
    """
    all_fields = extract_all_fields(records)
    table: Dict[str, Dict[str, Any]] = {field: {} for field in all_fields}

    for record in records:
        record_key = record.key
        for field in all_fields:
            table[field][record_key] = record.metadata.get(field)

    logger.info("Built native comparison table with %d fields across %d records", len(all_fields), len(records))
    return table


# -----------------------------
# Interpreted / extracted claims comparison
# -----------------------------

def extract_all_claim_types(claims: List[ExtractedClaim]) -> List[str]:
    """
    Union of semantic claim types across extracted claims.
    """
    return sorted(set(claim.claim_type for claim in claims))


def group_claims_by_record_and_type(claims: List[ExtractedClaim]) -> Dict[str, Dict[str, List[ExtractedClaim]]]:
    """
    Organize claims as:
        {
            record_key: {
                claim_type: [ExtractedClaim, ...]
            }
        }
    """
    grouped: Dict[str, Dict[str, List[ExtractedClaim]]] = {}

    for claim in claims:
        grouped.setdefault(claim.record_key, {})
        grouped[claim.record_key].setdefault(claim.claim_type, [])
        grouped[claim.record_key][claim.claim_type].append(claim)

    return grouped


def build_extracted_claims_table(
    claims: List[ExtractedClaim],
    record_keys: List[str] | None = None,
    use_normalized_values: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """
    Build an interpreted comparison table from extracted claims.

    Output shape:
        {
            "present_type": {
                "the_met:123": "claviorgan",
                "europeana:abc": "harpsichord | claviorgan",
            },
            "maker": {
                "the_met:123": "Herman Willenbrock",
                "europeana:abc": "Burkat Shudi",
            },
            ...
        }

    Args:
        claims: extracted claims from the selected subgraph
        record_keys: optional explicit record ordering/filter
        use_normalized_values: if True prefer normalized values, else raw values
    """
    if record_keys is None:
        record_keys = sorted(set(claim.record_key for claim in claims))

    all_claim_types = extract_all_claim_types(claims)
    grouped = group_claims_by_record_and_type(claims)

    table: Dict[str, Dict[str, Any]] = {claim_type: {} for claim_type in all_claim_types}

    for claim_type in all_claim_types:
        for record_key in record_keys:
            record_claims = grouped.get(record_key, {}).get(claim_type, [])

            if not record_claims:
                table[claim_type][record_key] = None
                continue

            values = []
            for claim in record_claims:
                value = claim.normalized_value if use_normalized_values else claim.raw_value
                value = normalize_field_value(value)
                if value:
                    values.append(value)

            # Deduplicate while preserving order
            seen = set()
            ordered_unique = []
            for v in values:
                if v not in seen:
                    seen.add(v)
                    ordered_unique.append(v)

            table[claim_type][record_key] = " | ".join(ordered_unique) if ordered_unique else None

    logger.info(
        "Built interpreted claims table with %d claim types across %d records",
        len(all_claim_types),
        len(record_keys),
    )
    return table


def build_claim_evidence_table(
    claims: List[ExtractedClaim],
    claim_types: List[str] | None = None,
) -> List[Dict[str, Any]]:
    """
    Build a row-oriented table for UI inspection of claims with evidence and confidence.

    Output rows like:
        {
            "record_key": "...",
            "claim_type": "former_type",
            "raw_value": "...",
            "normalized_value": "...",
            "evidence_span": "...",
            "confidence": 0.75,
            "extraction_method": "rule_based"
        }
    """
    rows: List[Dict[str, Any]] = []

    for claim in claims:
        if claim_types and claim.claim_type not in claim_types:
            continue

        rows.append({
            "claim_id": claim.claim_id,
            "record_key": claim.record_key,
            "source_field": claim.source_field,
            "claim_type": claim.claim_type,
            "raw_value": claim.raw_value,
            "normalized_value": claim.normalized_value,
            "evidence_span": claim.evidence_span,
            "confidence": claim.confidence,
            "extraction_method": claim.extraction_method,
        })

    return rows


# -----------------------------
# Grouping / display helpers
# -----------------------------

def group_claim_types_for_display(claims: List[ExtractedClaim]) -> Dict[str, List[str]]:
    """
    Group claim types into display buckets for the future UI.

    This keeps the interpreted comparison table more understandable.
    """
    present = set(claim.claim_type for claim in claims)

    buckets = {
        "typing_and_identity": [],
        "actors": [],
        "time": [],
        "materials": [],
        "events_and_history": [],
        "other": [],
    }

    for claim_type in sorted(present):
        if claim_type in {"present_type", "present_type_candidate", "former_type", "title", "alias", "subject_term"}:
            buckets["typing_and_identity"].append(claim_type)
        elif claim_type in {"maker", "maker_candidate", "creator", "actor"}:
            buckets["actors"].append(claim_type)
        elif claim_type in {"date_expression", "production_date_candidate"}:
            buckets["time"].append(claim_type)
        elif claim_type in {"material", "material_expression"}:
            buckets["materials"].append(claim_type)
        elif claim_type in {"copy_after", "intervention_event", "intervention_actor_candidate", "manual_configuration"}:
            buckets["events_and_history"].append(claim_type)
        else:
            buckets["other"].append(claim_type)

    return buckets


def get_claim_types_for_records(
    claims: List[ExtractedClaim],
    record_keys: Iterable[str],
) -> List[str]:
    """
    Claim types present for a given subset of record keys.
    """
    record_keys = set(record_keys)
    return sorted({
        claim.claim_type
        for claim in claims
        if claim.record_key in record_keys
    })
