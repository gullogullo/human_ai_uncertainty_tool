"""Semantic graph export helpers for JSON and RDF-oriented formats."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Tuple
from urllib.parse import quote

from src.semantic_graph import SemanticGraph, SemanticNode

BASE_URI = "https://remake.example.org/graph/"


def semantic_graph_to_dict(semantic_graph: SemanticGraph) -> Dict[str, Any]:
    return semantic_graph.to_dict()


def semantic_graph_to_json(semantic_graph: SemanticGraph, indent: int = 2) -> str:
    return json.dumps(semantic_graph_to_dict(semantic_graph), indent=indent, default=str)


def semantic_graph_node_uri(node: SemanticNode, base_uri: str = BASE_URI) -> str:
    return f"{base_uri}node/{quote(node.id)}"


def semantic_graph_triples(
    semantic_graph: SemanticGraph,
    base_uri: str = BASE_URI,
) -> List[Tuple[str, str, str, bool]]:
    triples: List[Tuple[str, str, str, bool]] = []

    for node in semantic_graph.nodes.values():
        subject = semantic_graph_node_uri(node, base_uri=base_uri)
        if node.crm_uri:
            triples.append((subject, "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", node.crm_uri, True))
        triples.append((subject, "http://www.w3.org/2000/01/rdf-schema#label", node.label, False))
        triples.append((subject, f"{base_uri}ontology/nodeType", node.node_type, False))
        triples.append((subject, f"{base_uri}ontology/crmClass", node.crm_class, False))
        if node.mimo_uri:
            triples.append((subject, "http://www.w3.org/2004/02/skos/core#exactMatch", node.mimo_uri, True))

    for edge in semantic_graph.edges:
        predicate = edge.crm_property_uri or f"{base_uri}predicate/{quote(edge.predicate.replace(' ', '_'))}"
        triples.append(
            (
                f"{base_uri}node/{quote(edge.source)}",
                predicate,
                f"{base_uri}node/{quote(edge.target)}",
                True,
            )
        )

    return triples


def semantic_graph_to_turtle(
    semantic_graph: SemanticGraph,
    base_uri: str = BASE_URI,
) -> str:
    try:
        from rdflib import Graph, Literal, Namespace, URIRef
        from rdflib.namespace import RDF, RDFS, SKOS

        graph = Graph()
        ns = Namespace(base_uri)
        graph.bind("remake", ns)
        graph.bind("rdfs", RDFS)
        graph.bind("rdf", RDF)
        graph.bind("skos", SKOS)

        for subj, pred, obj, is_resource in semantic_graph_triples(semantic_graph, base_uri=base_uri):
            subject = URIRef(subj)
            predicate = URIRef(pred)
            object_value = URIRef(obj) if is_resource else Literal(obj)
            graph.add((subject, predicate, object_value))

        return graph.serialize(format="turtle")
    except Exception:
        return _triples_to_turtle(semantic_graph_triples(semantic_graph, base_uri=base_uri))


def _triples_to_turtle(triples: Iterable[Tuple[str, str, str, bool]]) -> str:
    lines = [
        "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .",
        "",
    ]
    for subject, predicate, obj, is_resource in triples:
        object_text = f"<{obj}>" if is_resource else json.dumps(obj, ensure_ascii=False)
        lines.append(f"<{subject}> <{predicate}> {object_text} .")
    return "\n".join(lines) + "\n"
