"""Validation-gated uncertainty metrics."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

import numpy as np

from src.embeddings import compute_cosine_similarity, embed_text
from src.fields import IMAGE_RELEVANT_FIELDS, get_non_empty_values, normalize_field_value
from src.models import ExtractedClaim, Record, SignalResult, UncertaintyType

def build_claim_family_table(claims: List[ExtractedClaim]) -> Dict[str, Dict[str, str]]:
    table = defaultdict(dict)
    for claim in claims:
        current = table[claim.claim_type].get(claim.record_key, "")
        value = claim.normalized_value
        table[claim.claim_type][claim.record_key] = f"{current} | {value}".strip(" |") if current else value
    return dict(table)

def compute_missingness(comparison_table: Dict[str, Dict[str, Any]], field: str, total_items: int, record_keys: Optional[List[str]] = None) -> SignalResult:
    field_dict = comparison_table.get(field, {})
    non_empty = get_non_empty_values(field_dict)
    coverage = len(non_empty) / total_items if total_items else 0.0
    record_keys = record_keys or list(field_dict.keys())
    return SignalResult(
        field=field,
        uncertainty_type=UncertaintyType.MISSINGNESS,
        metric_name="coverage",
        metric_value=coverage,
        details={
            "record_keys_with_value": list(non_empty.keys()),
            "record_keys_missing": [k for k in record_keys if k not in non_empty],
            "total_items": total_items,
            "validated_scope": True,
        },
    )

def compute_textual_disagreement(comparison_table: Dict[str, Dict[str, Any]], field: str) -> SignalResult:
    field_dict = comparison_table.get(field, {})
    non_empty = get_non_empty_values(field_dict)
    if len(non_empty) < 2:
        return SignalResult(
            field=field,
            uncertainty_type=UncertaintyType.TEXTUAL_DISAGREEMENT,
            metric_name="avg_cosine_sim",
            metric_value=1.0,
            details={
                "reason": "insufficient_values",
                "distinct_value_count": len(set(normalize_field_value(v).lower() for v in non_empty.values())),
                "validated_scope": True,
            },
        )

    embeddings = {k: embed_text(v) for k, v in non_empty.items()}
    similarities = []
    keys = [k for k, emb in embeddings.items() if emb is not None]
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            sim = compute_cosine_similarity(embeddings[keys[i]], embeddings[keys[j]])
            if sim is not None:
                similarities.append(sim)

    avg = float(np.mean(similarities)) if similarities else 1.0
    normalized_by_record = {k: normalize_field_value(v).lower() for k, v in non_empty.items()}
    distinct_values = sorted(set(v for v in normalized_by_record.values() if v))
    value_variations = []
    if len(distinct_values) > 1:
        for key, value in normalized_by_record.items():
            value_variations.append(f"{key}: {value}")

    return SignalResult(
        field=field,
        uncertainty_type=UncertaintyType.TEXTUAL_DISAGREEMENT,
        metric_name="avg_textual_similarity",
        metric_value=avg,
        details={
            "num_pairs": len(similarities),
            "distinct_value_count": len(distinct_values),
            "value_variations": value_variations,
            "conflicts": value_variations,
            "validated_scope": True,
        },
    )

def compute_multimodal_consistency(records: List[Record], comparison_table: Dict[str, Dict[str, Any]], field: str) -> SignalResult:
    if field not in IMAGE_RELEVANT_FIELDS:
        return SignalResult(
            field=field,
            uncertainty_type=UncertaintyType.MULTIMODAL_CONSISTENCY,
            metric_name="avg_image_text_sim",
            metric_value=0.0,
            details={"reason": "field_not_image_relevant", "validated_scope": True},
        )

    from src.image_interpretation import compare_image_text_consistency, interpret_record_image
    scores = []
    comparisons = []
    row = comparison_table.get(field, {})
    for record in records:
        if not (record.image_url or record.local_image_path):
            continue
        textual_claims = {
            "title": record.title,
            "object_name": record.metadata.get("object_name") or record.metadata.get("object_type") or row.get(record.key, ""),
            "description": record.metadata.get("description", ""),
            "materials": record.metadata.get("materials") or record.metadata.get("material") or record.metadata.get("medium", ""),
        }
        if record.key in row and row[record.key]:
            textual_claims[field] = normalize_field_value(row[record.key])
        if not any(normalize_field_value(v) for v in textual_claims.values()):
            continue
        image_interpretation = record.raw.get("image_interpretation") if isinstance(record.raw, dict) else None
        if not image_interpretation:
            image_interpretation = interpret_record_image(record)
            if isinstance(record.raw, dict):
                record.raw["image_interpretation"] = image_interpretation
        comparison = compare_image_text_consistency(image_interpretation, textual_claims)
        comparisons.append({"record_key": record.key, "record_title": record.title, **comparison})
        scores.append(float(comparison.get("consistency_score", 0.5)))

    avg = float(np.mean(scores)) if scores else 0.0
    records_with_images = len([r for r in records if r.image_url or r.local_image_path])
    if avg >= 0.7:
        summary = "The visual observations broadly support visible object-type or material claims. This does not validate attribution, maker, date, provenance, or object identity."
    elif scores:
        summary = "The visual observations only partly support the textual object/material claims, or the vision layer was uncertain."
    else:
        summary = "No image interpretation was available for comparison."
    if not scores:
        summary = "No image interpretation was available for comparison."
    return SignalResult(
        field=field,
        uncertainty_type=UncertaintyType.MULTIMODAL_CONSISTENCY,
        metric_name="ai_image_text_consistency",
        metric_value=avg,
        details={
            "records_with_images": records_with_images,
            "num_comparisons": len(scores),
            "comparisons": comparisons,
            "summary": summary,
            "validated_scope": True,
        },
    )

def compute_all_signals(comparison_table: Dict[str, Dict[str, Any]], records: List[Record], selected_fields: Optional[List[str]] = None, uncertainty_types: Optional[List[UncertaintyType]] = None) -> List[SignalResult]:
    selected_fields = selected_fields or list(comparison_table.keys())
    uncertainty_types = uncertainty_types or list(UncertaintyType)
    total_items = len(records)
    record_keys = [r.key for r in records]
    out: List[SignalResult] = []

    for field in selected_fields:
        if UncertaintyType.MISSINGNESS in uncertainty_types:
            out.append(compute_missingness(comparison_table, field, total_items, record_keys=record_keys))
        if UncertaintyType.TEXTUAL_DISAGREEMENT in uncertainty_types:
            out.append(compute_textual_disagreement(comparison_table, field))
        if UncertaintyType.MULTIMODAL_CONSISTENCY in uncertainty_types:
            out.append(compute_multimodal_consistency(records, comparison_table, field))
    return out
