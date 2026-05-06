"""Helpers for querying the in-session semantic graph and remote SPARQL endpoints."""

from __future__ import annotations

from typing import Any, Dict, List

import requests

from src.export_semantic import BASE_URI, semantic_graph_to_turtle
from src.semantic_graph import SemanticGraph


def run_local_sparql_query(semantic_graph: SemanticGraph, query: str) -> List[Dict[str, Any]]:
    try:
        from rdflib import Graph
    except Exception as exc:
        raise RuntimeError("rdflib is required for local SPARQL queries.") from exc

    graph = Graph()
    graph.parse(data=semantic_graph_to_turtle(semantic_graph), format="turtle")

    rows: List[Dict[str, Any]] = []
    result = graph.query(query)
    for row in result:
        rows.append({str(var): str(row[var]) for var in result.vars})
    return rows


def query_remote_sparql_endpoint(
    endpoint_url: str,
    query: str,
    timeout: int = 20,
) -> List[Dict[str, Any]]:
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": "REMAKE/0.5 (human_ai_uncertainty_tool remote SPARQL client)",
    }

    response = requests.get(
        endpoint_url,
        params={"query": query, "format": "json"},
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()

    results: List[Dict[str, Any]] = []
    for binding in payload.get("results", {}).get("bindings", []):
        row = {}
        for key, value in binding.items():
            row[key] = value.get("value", "")
        results.append(row)
    return results


def default_local_sparql_query() -> str:
    return "\n".join(
        [
            "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>",
            "",
            "SELECT ?node ?label ?crmClass",
            "WHERE {",
            "  ?node rdfs:label ?label .",
            f"  ?node <{BASE_URI}ontology/crmClass> ?crmClass .",
            "}",
            "LIMIT 25",
        ]
    )


def default_remote_sparql_query() -> str:
    return "\n".join(
        [
            "SELECT ?s ?p ?o",
            "WHERE {",
            "  ?s ?p ?o .",
            "}",
            "LIMIT 25",
        ]
    )
