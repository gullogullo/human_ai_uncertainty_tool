"""Build semantic recommendations from validated claims."""

from __future__ import annotations

from typing import List

from src.models import ExtractedClaim, IdentityStatus, SemanticRecommendation
from src.semantic_templates import template_from_claim


SAME_OBJECT_STATUSES = {
    IdentityStatus.USER_ASSERTED_SAME_OBJECT.value,
    IdentityStatus.SOURCE_ASSERTED_SAME_OBJECT.value,
}


def _identity_value(identity_status) -> str:
    if isinstance(identity_status, IdentityStatus):
        return identity_status.value
    return identity_status or IdentityStatus.NO_IDENTITY_CLAIM.value


def _localize_template(template, claim: ExtractedClaim, identity_status: str) -> dict:
    if identity_status in SAME_OBJECT_STATUSES:
        return template

    localized = dict(template)
    label_map = {}
    localized_nodes = []

    for node in template["nodes"]:
        if node.node_type in {"semantic_object", "semantic_event"}:
            localized_label = f"{node.label} ({claim.record_key})"
            label_map[node.label] = localized_label
            node = type(node)(
                label=localized_label,
                node_type=node.node_type,
                crm_class=node.crm_class,
                crm_uri=node.crm_uri,
                mimo_uri=node.mimo_uri,
                attributes={**node.attributes, "record_key": claim.record_key, "scope": "record_local"},
            )
        localized_nodes.append(node)

    localized_edges = []
    for edge in template["edges"]:
        localized_edges.append(
            type(edge)(
                source_role=label_map.get(edge.source_role, edge.source_role),
                target_role=label_map.get(edge.target_role, edge.target_role),
                predicate=edge.predicate,
                crm_property=edge.crm_property,
                crm_property_uri=edge.crm_property_uri,
                notes=edge.notes,
            )
        )

    localized["nodes"] = localized_nodes
    localized["edges"] = localized_edges
    return localized


def _proposal_text(claim: ExtractedClaim, template, identity_status: str) -> dict:
    value = claim.normalized_value
    scope = "asserted_same_object" if identity_status in SAME_OBJECT_STATUSES else "record_local"
    risk_note = (
        "Same-object status permits this as an object-level assertion, but keep the source record provenance attached."
        if identity_status in SAME_OBJECT_STATUSES
        else "Do not apply this claim to other selected records unless identity is asserted."
    )

    if claim.claim_type == "maker":
        return {
            "action_label": "Add maker as production claim",
            "plain_language_claim": f"This record states that the object was made by '{value}'.",
            "scope": scope,
            "risk_note": risk_note,
            "crm_pattern": ["E22 Human-Made Object", "E12 Production", "P14 carried out by", "E39 Actor"],
        }
    if claim.claim_type == "date_expression":
        return {
            "action_label": "Add production date",
            "plain_language_claim": f"This record gives the production date as '{value}'.",
            "scope": scope,
            "risk_note": risk_note,
            "crm_pattern": ["E12 Production", "P4 has time-span", "E52 Time-Span"],
        }
    if claim.claim_type == "material":
        return {
            "action_label": "Add material as composition claim",
            "plain_language_claim": f"This record states that the object consists of '{value}'.",
            "scope": scope,
            "risk_note": risk_note,
            "crm_pattern": ["E22 Human-Made Object", "P45 consists of", "E57 Material"],
        }
    if claim.claim_type == "present_type":
        return {
            "action_label": "Add object type as classification",
            "plain_language_claim": f"This record states that the object is classified as '{value}'.",
            "scope": scope,
            "risk_note": risk_note,
            "crm_pattern": ["E22 Human-Made Object", "P2 has type", "E55 Type"],
        }
    return {
        "action_label": template["label"],
        "plain_language_claim": f"This record states '{value}'.",
        "scope": scope,
        "risk_note": risk_note,
        "crm_pattern": [template["vocabulary_hint"]],
    }


def recommend_from_claims(
    claims: List[ExtractedClaim],
    identity_status=IdentityStatus.NO_IDENTITY_CLAIM.value,
) -> List[SemanticRecommendation]:
    recommendations: List[SemanticRecommendation] = []
    identity_status = _identity_value(identity_status)

    for idx, claim in enumerate(claims, start=1):
        template = template_from_claim(claim)
        if not template:
            continue
        template = _localize_template(template, claim, identity_status)
        proposal_text = _proposal_text(claim, template, identity_status)

        recommendations.append(
            SemanticRecommendation(
                recommendation_id=f"rec:{idx}",
                claim_id=claim.claim_id,
                source_record_key=claim.record_key,
                pattern_id=template["pattern_id"],
                label=template["label"],
                confidence=claim.confidence,
                requires_human_validation=claim.requires_human_validation,
                vocabulary_hint=template["vocabulary_hint"],
                explanation=template["explanation"],
                nodes=template["nodes"],
                edges=template["edges"],
                provenance_note=f"Derived from {claim.source_field} on {claim.record_key}",
                action_label=proposal_text["action_label"],
                plain_language_claim=proposal_text["plain_language_claim"],
                scope=proposal_text["scope"],
                provenance_record_key=claim.record_key,
                source_field=claim.source_field,
                risk_note=proposal_text["risk_note"],
                crm_pattern=proposal_text["crm_pattern"],
                preview_nodes=template["nodes"],
                preview_edges=template["edges"],
            )
        )

    return recommendations
