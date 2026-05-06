"""Claim extraction layer for the evidence graph.

This module turns source-native metadata and free-text descriptions into
ExtractedClaim objects that can later feed:
- interpreted comparison tables
- semantic recommendations
- the user-built semantic workspace graph
"""

from __future__ import annotations

import re
from typing import List

from src.fields import normalize_field_value
from src.models import ExtractedClaim, Record, ValidatedFieldMapping

def extract_claims(records: List[Record], mappings: List[ValidatedFieldMapping]) -> List[ExtractedClaim]:
    claims: List[ExtractedClaim] = []
    mapping_by_field = {}
    for mapping in mappings:
        if not mapping.approved:
            continue
        for field in mapping.source_fields:
            mapping_by_field[field] = mapping.claim_type

    for record in records:
        for field, value in record.metadata.items():
            if field not in mapping_by_field:
                continue
            norm = normalize_field_value(value)
            if not norm:
                continue
            claim_type = mapping_by_field[field]
            claims.append(
                ExtractedClaim(
                    claim_id=f"{record.key}:{field}:{len(claims)+1}",
                    record_key=record.key,
                    source_field=field,
                    claim_type=claim_type,
                    raw_value=value,
                    normalized_value=norm,
                    evidence_span=norm[:120],
                    confidence=0.85 if field != "description" else 0.55,
                    extraction_method="structured_field" if field != "description" else "description_rule",
                    requires_human_validation=(field == "description"),
                )
            )

        description = normalize_field_value(record.metadata.get("description"))
        if description:
            for pattern in [r"\bmade by ([A-Z][A-Za-z .'-]+)", r"\bbuilt by ([A-Z][A-Za-z .'-]+)"]:
                match = re.search(pattern, description)
                if match:
                    claims.append(
                        ExtractedClaim(
                            claim_id=f"{record.key}:description-maker:{len(claims)+1}",
                            record_key=record.key,
                            source_field="description",
                            claim_type="maker",
                            raw_value=match.group(1),
                            normalized_value=match.group(1).strip(),
                            evidence_span=match.group(0),
                            confidence=0.55,
                            extraction_method="description_rule",
                            requires_human_validation=True,
                        )
                    )
                    break

        image_review = record.human_validations.get("image_interpretation", {}) if record.human_validations else {}
        image_interpretation = record.raw.get("image_interpretation", {}) if isinstance(record.raw, dict) else {}
        if image_review.get("decision") == "Accept" and image_interpretation:
            proposed = {
                "present_type": image_interpretation.get("visible_object_type"),
                "material": " | ".join(image_interpretation.get("visible_materials") or []),
                "description": image_review.get("edited_caption") or image_interpretation.get("caption"),
            }
            for claim_type, value in proposed.items():
                norm = normalize_field_value(value)
                if not norm:
                    continue
                claims.append(
                    ExtractedClaim(
                        claim_id=f"{record.key}:image-{claim_type}:{len(claims)+1}",
                        record_key=record.key,
                        source_field="image_interpretation",
                        claim_type=claim_type,
                        raw_value=value,
                        normalized_value=norm,
                        evidence_span=image_interpretation.get("caption") or norm[:120],
                        confidence=0.5,
                        extraction_method="image_interpretation",
                        requires_human_validation=False,
                    )
                )

        visual_review = record.human_validations.get("visual_indexing", {}) if record.human_validations else {}
        visual_indexing = record.raw.get("visual_indexing", {}) if isinstance(record.raw, dict) else {}
        alignment = record.raw.get("image_text_alignment", {}) if isinstance(record.raw, dict) else {}
        if visual_review.get("decision") == "Accept" and visual_indexing:
            accepted_labels = visual_review.get("accepted_labels") or []
            if not accepted_labels:
                accepted_labels = visual_indexing.get("top_labels", [])[:3]
            for idx, label_result in enumerate(accepted_labels, start=1):
                if not isinstance(label_result, dict):
                    continue
                claim_type = label_result.get("claim_type") or "description"
                value = label_result.get("claim_value") or label_result.get("label")
                norm = normalize_field_value(value)
                if not norm:
                    continue
                score = float(label_result.get("score") or 0.0)
                claims.append(
                    ExtractedClaim(
                        claim_id=f"{record.key}:visual-{claim_type}-{idx}:{len(claims)+1}",
                        record_key=record.key,
                        source_field="visual_indexing",
                        claim_type=claim_type,
                        raw_value=label_result,
                        normalized_value=norm,
                        evidence_span=(
                            f"{visual_indexing.get('method', 'visual_indexing')} "
                            f"{visual_indexing.get('model', '')}; score={score:.3f}; "
                            f"alignment={alignment.get('overall_alignment', 'uncertain')}"
                        ),
                        confidence=max(0.3, min(0.75, score + 0.25)),
                        extraction_method="visual_indexing",
                        requires_human_validation=False,
                    )
                )
            alignment_value = alignment.get("overall_alignment")
            if alignment_value:
                claims.append(
                    ExtractedClaim(
                        claim_id=f"{record.key}:visual-alignment:{len(claims)+1}",
                        record_key=record.key,
                        source_field="image_text_alignment",
                        claim_type="image_text_alignment",
                        raw_value=alignment,
                        normalized_value=alignment_value,
                        evidence_span=(
                            f"supports={len(alignment.get('supports') or [])}; "
                            f"conflicts={len(alignment.get('conflicts') or [])}; "
                            f"unmentioned={len(alignment.get('unmentioned_visual_observations') or [])}"
                        ),
                        confidence=float(alignment.get("alignment_score") or 0.5),
                        extraction_method="visual_indexing_alignment",
                        requires_human_validation=False,
                    )
                )
    return claims
