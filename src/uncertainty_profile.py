"""Profile builder reordered around schema inspection, evidence interrogation, and validation."""

from __future__ import annotations

from dataclasses import asdict
from typing import List, Optional

from src.alignment import get_comparable_records
from src.claim_extraction import extract_claims
from src.fields import default_validated_mappings, make_comparison_table_arrow_safe
from src.models import Record, UncertaintyProfile, UncertaintyType, ValidatedFieldMapping
from src.prompts import generate_prompts
from src.schema_inspection import build_schema_matrix
from src.signals import build_claim_family_table, compute_all_signals

def build_profile(query: str, records: List[Record], selected_fields: Optional[List[str]] = None, uncertainty_types: Optional[List[UncertaintyType]] = None, validated_mappings: Optional[List[ValidatedFieldMapping]] = None, compute_signals: bool = False) -> UncertaintyProfile:
    comparable_records = get_comparable_records(records)
    schema_matrix = build_schema_matrix(comparable_records) if comparable_records else None

    if validated_mappings is None:
        validated_mappings = [ValidatedFieldMapping(**item) for item in default_validated_mappings(comparable_records)]

    extracted_claims = extract_claims(comparable_records, validated_mappings)
    raw_table = build_claim_family_table(extracted_claims)
    signals = []
    prompts = []

    if compute_signals:
        fields = selected_fields or list(raw_table.keys())
        signals = compute_all_signals(raw_table, comparable_records, selected_fields=fields, uncertainty_types=uncertainty_types)
        prompts = generate_prompts(signals)

    return UncertaintyProfile(
        query=query,
        selected_record_keys=[r.key for r in comparable_records],
        schema_matrix=schema_matrix,
        validated_mappings=validated_mappings,
        comparison_table=make_comparison_table_arrow_safe(raw_table),
        all_fields=list(raw_table.keys()),
        extracted_claims=extracted_claims,
        signals=signals,
        prompts=prompts,
    )

def get_high_uncertainty_fields(profile: UncertaintyProfile) -> List[str]:
    concerns = {}
    for signal in profile.signals:
        concerns.setdefault(signal.field, []).append(1 - signal.metric_value)
    ranked = sorted(((field, sum(vals) / len(vals)) for field, vals in concerns.items()), key=lambda x: x[1], reverse=True)
    return [field for field, _ in ranked]
