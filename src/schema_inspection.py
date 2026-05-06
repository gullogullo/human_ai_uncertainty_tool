"""Schema-first inspection helpers."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from src.fields import HIDDEN_ANALYSIS_FIELDS, infer_field_family
from src.models import Record, SchemaMatrix

def build_schema_matrix(records: List[Record]) -> SchemaMatrix:
    fields_by_source: Dict[str, set] = defaultdict(set)
    grouped_fields: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))

    for record in records:
        for field in record.metadata.keys():
            if field in HIDDEN_ANALYSIS_FIELDS:
                continue
            fields_by_source[record.source].add(field)

    all_fields = sorted({field for fields in fields_by_source.values() for field in fields})
    presence_rows = []
    for field in all_fields:
        row = {"field": field, "field_family": infer_field_family(field)}
        for source, source_fields in fields_by_source.items():
            row[source] = field in source_fields
            if field in source_fields:
                group = record.source_schema.field_groups.get(field, "other") if record.source_schema else "other"
                grouped_fields[source][group].append(field)
        presence_rows.append(row)

    return SchemaMatrix(
        sources=sorted(fields_by_source.keys()),
        fields_by_source={src: sorted(v) for src, v in fields_by_source.items()},
        presence_rows=presence_rows,
        grouped_fields={src: {grp: sorted(set(vals)) for grp, vals in groups.items()} for src, groups in grouped_fields.items()},
    )
