"""CIDOC-CRM + MIMO grounded semantic templates."""

from __future__ import annotations

from typing import Dict, Optional

from src.models import SemanticEdgeSpec, SemanticNodeSpec

CIDOC = {
    "E22": "https://cidoc-crm.org/Entity/e22-human-made-object/version-7.1",
    "E12": "https://cidoc-crm.org/Entity/e12-production/version-7.1.1",
    "E39": "https://cidoc-crm.org/Entity/e39-actor/version-6.2",
    "E52": "https://cidoc-crm.org/Entity/e52-time-span/version-6.2.1",
    "E57": "https://cidoc-crm.org/Entity/e57-material/version-6.2",
    "E55": "https://cidoc-crm.org/cidoc-crm/",
}

CIDOC_PROP = {
    "P108": "https://cidoc-crm.org/Property/p108-has-produced/version-5.0.2",
    "P14": "https://cidoc-crm.org/cidoc-crm/",
    "P4": "https://cidoc-crm.org/Property/p4-has-time-span/version-7.1",
    "P45": "https://cidoc-crm.org/Property/p45-consists-of/version-7.1.1",
    "P2": "https://cidoc-crm.org/Property/p2-has-type/version-7.1",
}

MIMO = {
    "harpsichord": {
        "uri": "http://www.mimo-db.eu/HornbostelAndSachs/314",
        "label": "Board zithers",
        "notation": "314",
    },
    "claviorgan": {
        "uri": None,
        "label": "Hybrid keyboard instrument; needs researcher selection in Hornbostel-Sachs/MIMO",
        "notation": None,
    },
    "oboe": {
        "uri": "http://www.mimo-db.eu/HornbostelAndSachs/422.112",
        "label": "(Single) oboes with conical bore",
        "notation": "422.112",
    },
}


def pattern_for_maker(claim) -> Dict[str, object]:
    return {
        "pattern_id": "crm_e12_production_maker",
        "label": "Production with maker",
        "vocabulary_hint": "CIDOC-CRM backbone",
        "explanation": (
            "A maker should not be attached as a flat literal. "
            "The recommendation models instrument making as an E12 Production event, "
            "linked to the instrument and the actor."
        ),
        "nodes": [
            SemanticNodeSpec("Instrument", "semantic_object", "E22", CIDOC["E22"]),
            SemanticNodeSpec(claim.normalized_value, "semantic_actor", "E39", CIDOC["E39"]),
            SemanticNodeSpec("Production", "semantic_event", "E12", CIDOC["E12"]),
        ],
        "edges": [
            SemanticEdgeSpec("Production", "Instrument", "has produced", "P108", CIDOC_PROP["P108"]),
            SemanticEdgeSpec("Production", claim.normalized_value, "carried out by", "P14", CIDOC_PROP["P14"]),
        ],
    }


def pattern_for_date(claim) -> Dict[str, object]:
    return {
        "pattern_id": "crm_e12_timespan",
        "label": "Production time-span",
        "vocabulary_hint": "CIDOC-CRM backbone",
        "explanation": (
            "A date expression is modeled as a time-span attached to the production event, "
            "not as a plain string attached directly to the instrument."
        ),
        "nodes": [
            SemanticNodeSpec("Production", "semantic_event", "E12", CIDOC["E12"]),
            SemanticNodeSpec(claim.normalized_value, "semantic_time", "E52", CIDOC["E52"]),
        ],
        "edges": [
            SemanticEdgeSpec("Production", claim.normalized_value, "has time-span", "P4", CIDOC_PROP["P4"]),
        ],
    }


def pattern_for_material(claim) -> Dict[str, object]:
    return {
        "pattern_id": "crm_material",
        "label": "Object material",
        "vocabulary_hint": "CIDOC-CRM backbone",
        "explanation": (
            "A material statement is modeled as the instrument consisting of a material, "
            "rather than as an untyped note."
        ),
        "nodes": [
            SemanticNodeSpec("Instrument", "semantic_object", "E22", CIDOC["E22"]),
            SemanticNodeSpec(claim.normalized_value, "semantic_material", "E57", CIDOC["E57"]),
        ],
        "edges": [
            SemanticEdgeSpec("Instrument", claim.normalized_value, "consists of", "P45", CIDOC_PROP["P45"]),
        ],
    }


def pattern_for_present_type(claim) -> Dict[str, object]:
    mimo = MIMO.get(claim.normalized_value.strip().lower(), {})
    return {
        "pattern_id": "crm_type_with_mimo_hint",
        "label": "Object type with MIMO hint",
        "vocabulary_hint": "CIDOC-CRM + MIMO Hornbostel-Sachs",
        "explanation": (
            "A present type is modeled as an E55 Type linked to the instrument with P2 has type. "
            "If a MIMO Hornbostel-Sachs concept is known, it is attached as a vocabulary hint; "
            "otherwise the researcher should refine it manually."
        ),
        "nodes": [
            SemanticNodeSpec("Instrument", "semantic_object", "E22", CIDOC["E22"]),
            SemanticNodeSpec(
                claim.normalized_value,
                "semantic_type",
                "E55",
                CIDOC["E55"],
                mimo.get("uri"),
                {"mimo_label": mimo.get("label"), "mimo_notation": mimo.get("notation")},
            ),
        ],
        "edges": [
            SemanticEdgeSpec("Instrument", claim.normalized_value, "has type", "P2", CIDOC_PROP["P2"]),
        ],
    }


def template_from_claim(claim) -> Optional[Dict[str, object]]:
    if claim.claim_type == "maker":
        return pattern_for_maker(claim)
    if claim.claim_type == "date_expression":
        return pattern_for_date(claim)
    if claim.claim_type == "material":
        return pattern_for_material(claim)
    if claim.claim_type == "present_type":
        return pattern_for_present_type(claim)
    return None