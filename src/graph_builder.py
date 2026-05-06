"""Evidence graph builder with compact/full modes and explicit edge semantics."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from src.fields import HIDDEN_ANALYSIS_FIELDS, normalize_field_value, tokenize
from src.models import EvidenceGraph, GraphEdge, GraphNode, NodeType, Record

TEXT_FIELDS_FOR_LINKING = {"title", "description", "object_name", "subject", "aliases_en"}

def build_evidence_graph(query: str, search_results: Dict[str, List[Record]], include_claim_nodes: bool = False) -> EvidenceGraph:
    all_records: List[Record] = [record for records in search_results.values() for record in records]
    graph = EvidenceGraph(query=query, records=all_records)

    query_id = f"query:{query.strip().lower()}"
    graph.nodes.append(GraphNode(node_id=query_id, node_type=NodeType.QUERY, label=query, payload={"query": query}))

    for record in all_records:
        _add_record_subgraph(graph, query_id, record, include_claim_nodes=include_claim_nodes)

    _add_cross_record_links(graph, all_records)
    return graph

def add_record_to_graph(graph: EvidenceGraph, record: Record, include_claim_nodes: bool = False) -> None:
    """Add one externally supplied record as a separate witness in an existing graph."""
    existing_records = list(graph.records)
    graph.records.append(record)
    query_node_id = f"query:{graph.query.strip().lower()}"
    _add_record_subgraph(graph, query_node_id, record, include_claim_nodes=include_claim_nodes)
    for existing in existing_records:
        relation, weight, evidence = infer_record_relation(existing, record)
        if relation:
            graph.edges.append(
                GraphEdge(
                    source_id=f"record:{existing.key}",
                    target_id=f"record:{record.key}",
                    relation=relation,
                    weight=weight or 1.0,
                    evidence=evidence or {},
                )
            )

def _add_record_subgraph(graph: EvidenceGraph, query_node_id: str, record: Record, include_claim_nodes: bool = False) -> None:
    record_node_id = f"record:{record.key}"
    node_type = NodeType.CONCEPT if record.is_semantic_anchor else NodeType.RECORD

    graph.nodes.append(
        GraphNode(
            node_id=record_node_id,
            node_type=node_type,
            label=record.title,
            payload={
                "record_key": record.key,
                "source": record.source,
                "source_schema": record.source_schema.schema_name if record.source_schema else "",
                "retrieval_class": record.retrieval_class,
                "is_semantic_anchor": record.is_semantic_anchor,
                "source_url": record.source_url or "",
                "image_url": record.image_url or "",
                "title": record.title,
                "metadata": record.metadata,
                "object_id": record.object_id,
            },
        )
    )
    graph.edges.append(
        GraphEdge(
            source_id=query_node_id,
            target_id=record_node_id,
            relation=record.retrieval_class,
            evidence={
                "edge_family": "retrieval",
                "meaning": retrieval_edge_meaning(record.retrieval_class),
            },
        )
    )

    if record.image_url:
        media_node_id = f"media:{record.key}"
        graph.nodes.append(GraphNode(node_id=media_node_id, node_type=NodeType.MEDIA, label="media", payload={"record_key": record.key, "image_url": record.image_url, "record_title": record.title}))
        graph.edges.append(GraphEdge(source_id=record_node_id, target_id=media_node_id, relation="has_media", evidence={"edge_family": "structural"}))

    if not include_claim_nodes:
        return

    for field, value in record.metadata.items():
        if field in HIDDEN_ANALYSIS_FIELDS:
            continue
        claim_text = normalize_field_value(value)
        if not claim_text:
            continue
        claim_node_id = f"claim:{record.key}:{field}"
        graph.nodes.append(
            GraphNode(
                node_id=claim_node_id,
                node_type=NodeType.CLAIM,
                label=f"{field}: {claim_text[:70]}",
                payload={
                    "record_key": record.key,
                    "field": field,
                    "value": claim_text,
                    "source_record_title": record.title,
                    "source_url": record.source_url or "",
                },
            )
        )
        graph.edges.append(GraphEdge(source_id=record_node_id, target_id=claim_node_id, relation="has_claim", evidence={"edge_family": "structural"}))

def _add_cross_record_links(graph: EvidenceGraph, records: List[Record]) -> None:
    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            relation, weight, evidence = infer_record_relation(records[i], records[j])
            if relation:
                graph.edges.append(
                    GraphEdge(
                        source_id=f"record:{records[i].key}",
                        target_id=f"record:{records[j].key}",
                        relation=relation,
                        weight=weight or 1.0,
                        evidence=evidence or {},
                    )
                )

def infer_record_relation(r1: Record, r2: Record) -> Tuple[Optional[str], Optional[float], Optional[dict]]:
    t1 = normalize_field_value(r1.metadata.get("title") or r1.title).lower()
    t2 = normalize_field_value(r2.metadata.get("title") or r2.title).lower()

    aliases_1 = set(a.lower() for a in (r1.metadata.get("aliases_en") or []) if isinstance(a, str))
    aliases_2 = set(a.lower() for a in (r2.metadata.get("aliases_en") or []) if isinstance(a, str))

    if t1 and t2 and t1 == t2:
        return "same_title_candidate", 0.95, {"edge_family": "inferred_record_link", "reason": "exact_title_match"}
    if t1 in aliases_2 or t2 in aliases_1:
        return "alias_match", 0.9, {"edge_family": "inferred_record_link", "reason": "title_alias_match"}

    shared_terms = shared_metadata_terms(r1, r2)
    if shared_terms:
        return "shares_term_with", 0.65, {"edge_family": "inferred_record_link", "shared_terms": sorted(shared_terms)[:10]}

    if mentions_each_other(r1, r2):
        return "description_relation", 0.6, {"edge_family": "inferred_record_link", "reason": "cross_description_mention"}

    return None, None, None

def shared_metadata_terms(r1: Record, r2: Record) -> set:
    return metadata_token_set(r1).intersection(metadata_token_set(r2)) - stop_terms()

def metadata_token_set(record: Record) -> set:
    values = []
    for field, value in record.metadata.items():
        if field in HIDDEN_ANALYSIS_FIELDS or field not in TEXT_FIELDS_FOR_LINKING:
            continue
        values.append(normalize_field_value(value).lower())
    return {token for value in values for token in tokenize(value)}

def mentions_each_other(r1: Record, r2: Record) -> bool:
    desc_1 = normalize_field_value(r1.metadata.get("description")).lower()
    desc_2 = normalize_field_value(r2.metadata.get("description")).lower()
    title_1 = (r1.title or "").lower()
    title_2 = (r2.title or "").lower()
    return (title_1 and title_1 in desc_2) or (title_2 and title_2 in desc_1)

def stop_terms() -> set:
    return {"with", "from", "that", "this", "have", "been", "were", "instrument", "object", "image", "various", "materials"}

def retrieval_edge_meaning(relation: str) -> str:
    meanings = {
        "exact_title_match": "The query exactly matches the returned title.",
        "title_match": "The query appears inside the title.",
        "alias_match": "The query matched an alias or alternate label.",
        "description_match": "The query appears in the description text.",
        "subject_match": "The query appears in a subject field.",
        "retrieval_match": "The API returned the record even though no more specific textual match rule fired.",
        "non_api_curated": "The record came from a non-API curated source or fallback dataset.",
        "manual_user_added": "The record was added manually by the user.",
        "same_title_candidate": "Unvalidated retrieval cue: two records share the same title.",
        "shares_term_with": "Unvalidated retrieval cue: two records share metadata terms.",
        "description_relation": "Unvalidated retrieval cue: one record text appears to mention the other.",
        "has_media": "The record has associated multimedia.",
        "has_claim": "The record has a visible metadata claim node.",
    }
    return meanings.get(relation, relation)
