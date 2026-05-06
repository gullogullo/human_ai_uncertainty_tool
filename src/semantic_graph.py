from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List
import uuid


@dataclass
class SemanticNode:
    id: str
    label: str
    node_type: str
    crm_class: str
    crm_uri: str = ""
    mimo_uri: str = ""


@dataclass
class SemanticEdge:
    source: str
    target: str
    predicate: str
    crm_property: str = ""
    crm_property_uri: str = ""


@dataclass
class SemanticGraph:
    nodes: Dict[str, SemanticNode] = field(default_factory=dict)
    edges: List[SemanticEdge] = field(default_factory=list)
    provenance: List[dict] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": {node_id: asdict(node) for node_id, node in self.nodes.items()},
            "edges": [asdict(edge) for edge in self.edges],
            "provenance": list(self.provenance),
        }


def create_empty_graph() -> SemanticGraph:
    return SemanticGraph()


def _edge_key(edge: SemanticEdge):
    return (
        edge.source,
        edge.target,
        edge.predicate,
        edge.crm_property,
        edge.crm_property_uri,
    )


def _get_or_create_node(graph: SemanticGraph, node_spec) -> tuple[str, bool]:
    for node in graph.nodes.values():
        if node.label == node_spec.label and node.node_type == node_spec.node_type:
            return node.id, False

    node_id = str(uuid.uuid4())
    graph.nodes[node_id] = SemanticNode(
        id=node_id,
        label=node_spec.label,
        node_type=node_spec.node_type,
        crm_class=node_spec.crm_class,
        crm_uri=getattr(node_spec, "crm_uri", ""),
        mimo_uri=getattr(node_spec, "mimo_uri", ""),
    )
    return node_id, True


def add_recommendation(graph: SemanticGraph, rec) -> SemanticGraph:
    role_map = {}
    node_ids_added = []
    edge_keys_added = []

    for node_spec in rec.nodes:
        node_id, created = _get_or_create_node(graph, node_spec)
        role_map[node_spec.label] = node_id
        if created:
            node_ids_added.append(node_id)

    existing_edges = {
        (
            edge.source,
            edge.target,
            edge.predicate,
            edge.crm_property,
            edge.crm_property_uri,
        )
        for edge in graph.edges
    }

    for edge_spec in rec.edges:
        source = role_map.get(edge_spec.source_role)
        target = role_map.get(edge_spec.target_role)

        if not source or not target:
            continue

        edge_key = (
            source,
            target,
            edge_spec.predicate,
            edge_spec.crm_property,
            edge_spec.crm_property_uri,
        )
        if edge_key in existing_edges:
            continue

        graph.edges.append(
            SemanticEdge(
                source=source,
                target=target,
                predicate=edge_spec.predicate,
                crm_property=edge_spec.crm_property,
                crm_property_uri=edge_spec.crm_property_uri,
            )
        )
        existing_edges.add(edge_key)
        edge_keys_added.append(list(edge_key))

    provenance_item = {
        "recommendation_id": rec.recommendation_id,
        "claim_id": rec.claim_id,
        "record": rec.source_record_key,
        "scope": getattr(rec, "scope", "record_local"),
        "provenance_record_key": getattr(rec, "provenance_record_key", rec.source_record_key),
        "source_field": getattr(rec, "source_field", ""),
        "plain_language_claim": getattr(rec, "plain_language_claim", ""),
        "risk_note": getattr(rec, "risk_note", ""),
        "node_ids_added": node_ids_added,
        "edge_keys_added": edge_keys_added,
    }
    if provenance_item not in graph.provenance:
        graph.provenance.append(provenance_item)

    return graph


def remove_recommendation(graph: SemanticGraph, recommendation_id: str) -> SemanticGraph:
    matching_items = [
        item
        for item in graph.provenance
        if item.get("recommendation_id") == recommendation_id
    ]
    if not matching_items:
        return graph

    remaining_provenance = [
        item
        for item in graph.provenance
        if item.get("recommendation_id") != recommendation_id
    ]

    protected_edge_keys = {
        tuple(edge_key)
        for item in remaining_provenance
        for edge_key in item.get("edge_keys_added", [])
    }
    removable_edge_keys = {
        tuple(edge_key)
        for item in matching_items
        for edge_key in item.get("edge_keys_added", [])
    }
    graph.edges = [
        edge
        for edge in graph.edges
        if _edge_key(edge) not in removable_edge_keys or _edge_key(edge) in protected_edge_keys
    ]

    protected_node_ids = {
        node_id
        for item in remaining_provenance
        for node_id in item.get("node_ids_added", [])
    }
    connected_node_ids = {
        node_id
        for edge in graph.edges
        for node_id in (edge.source, edge.target)
    }
    removable_node_ids = {
        node_id
        for item in matching_items
        for node_id in item.get("node_ids_added", [])
    }
    for node_id in removable_node_ids:
        if node_id not in protected_node_ids and node_id not in connected_node_ids:
            graph.nodes.pop(node_id, None)

    graph.provenance = remaining_provenance
    return graph


def merge_nodes(graph: SemanticGraph, source_node_id: str, target_node_id: str) -> SemanticGraph:
    if source_node_id == target_node_id:
        return graph
    if source_node_id not in graph.nodes or target_node_id not in graph.nodes:
        return graph

    existing_edges = set()
    merged_edges: List[SemanticEdge] = []

    for edge in graph.edges:
        new_source = target_node_id if edge.source == source_node_id else edge.source
        new_target = target_node_id if edge.target == source_node_id else edge.target

        if new_source == new_target:
            continue

        edge_key = (
            new_source,
            new_target,
            edge.predicate,
            edge.crm_property,
            edge.crm_property_uri,
        )
        if edge_key in existing_edges:
            continue

        existing_edges.add(edge_key)
        merged_edges.append(
            SemanticEdge(
                source=new_source,
                target=new_target,
                predicate=edge.predicate,
                crm_property=edge.crm_property,
                crm_property_uri=edge.crm_property_uri,
            )
        )

    graph.edges = merged_edges

    source_node = graph.nodes.pop(source_node_id)
    graph.provenance.append(
        {
            "action": "merge_nodes",
            "source_node_id": source_node_id,
            "target_node_id": target_node_id,
            "source_label": source_node.label,
            "target_label": graph.nodes[target_node_id].label,
        }
    )

    return graph


def semantic_node_choices(graph: SemanticGraph) -> List[tuple[str, str]]:
    return sorted(
        (
            node_id,
            f"{node.label} [{node.node_type}] ({node_id[:8]})",
        )
        for node_id, node in graph.nodes.items()
    )
