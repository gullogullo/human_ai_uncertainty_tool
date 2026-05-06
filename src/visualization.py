"""Readable PyVis rendering with stabilized layout, human-readable tooltips, and improved interaction."""

from __future__ import annotations

import os
import tempfile
from pyvis.network import Network

from src.graph_builder import retrieval_edge_meaning
from src.models import EvidenceGraph, NodeType
from src.settings import DEBUG_UI

NODE_STYLE = {
    NodeType.QUERY.value: {"color": "#D97706", "shape": "star", "size": 28},
    NodeType.RECORD.value: {"color": "#2563EB", "shape": "dot", "size": 22},
    NodeType.CONCEPT.value: {"color": "#7C3AED", "shape": "diamond", "size": 24},
    NodeType.MEDIA.value: {"color": "#059669", "shape": "triangle", "size": 16},
    NodeType.CLAIM.value: {"color": "#6B7280", "shape": "box", "size": 13},
}

EDGE_STYLE = {
    "exact_title_match": {"color": "#1D4ED8", "width": 4, "dashes": False},
    "title_match": {"color": "#2563EB", "width": 3, "dashes": False},
    "alias_match": {"color": "#7C3AED", "width": 3, "dashes": True},
    "description_match": {"color": "#0891B2", "width": 2, "dashes": True},
    "subject_match": {"color": "#0F766E", "width": 2, "dashes": True},
    "retrieval_match": {"color": "#9CA3AF", "width": 1, "dashes": True},
    "has_media": {"color": "#059669", "width": 2, "dashes": False},
    "has_claim": {"color": "#9CA3AF", "width": 1, "dashes": True},
    "same_title_candidate": {"color": "#DC2626", "width": 2, "dashes": False},
    "shares_term_with": {"color": "#F59E0B", "width": 1, "dashes": True},
    "description_relation": {"color": "#0EA5E9", "width": 1, "dashes": True},
}

EDGE_LABEL_MAP = {
    "exact_title_match": "≈ exact match",
    "title_match": "~ title match",
    "alias_match": "~ alias",
    "description_match": "→ in description",
    "subject_match": "→ in subjects",
    "retrieval_match": "retrieved",
    "non_api_curated": "curated source",
    "manual_user_added": "user added",
    "has_media": "has media",
    "has_claim": "has claim",
    "same_title_candidate": "same title",
    "shares_term_with": "shared term",
    "description_relation": "text mention",
}

def build_pyvis_graph(graph: EvidenceGraph, height: str = "760px", width: str = "100%") -> Network:
    """
    Build a PyVis network with stabilized physics, readable tooltips, and human-friendly labels.
    """
    net = Network(height=height, width=width, directed=False, notebook=False)
    
    # Configure with reduced physics and stabilization
    net.set_options("""
    const options = {
      "layout": {"improvedLayout": true, "randomSeed": 42},
      "nodes": {
        "font": {"size": 16, "multi": "html"},
        "scaling": {"label": {"enabled": true, "min": 14, "max": 30}}
      },
      "edges": {
        "font": {"size": 11, "color": "#555", "multi": "html"},
        "smooth": {"enabled": true, "type": "continuous"},
        "color": {"inherit": false}
      },
      "physics": {
        "enabled": true,
        "stabilization": {
          "enabled": true,
          "iterations": 150,
          "updateInterval": 25,
          "fit": true
        },
        "barnesHut": {
          "gravitationalConstant": -4000,
          "centralGravity": 0.3,
          "springLength": 200,
          "springConstant": 0.008,
          "damping": 0.4
        },
        "timeStep": 0.5,
        "adaptiveTimestep": true
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 150,
        "hideEdgesOnDrag": false,
        "hideEdgesOnZoom": false,
        "dragNodes": true,
        "navigationButtons": false,
        "keyboard": false,
        "zoomView": false,
        "dragView": false
      }
    }
    """)

    for node in graph.nodes:
        style = NODE_STYLE.get(node.node_type.value, {"color": "#9CA3AF", "shape": "dot", "size": 16})
        net.add_node(
            node.node_id,
            label=_display_label(node),
            title=_build_node_tooltip(node),
            color=style["color"],
            shape=style["shape"],
            size=style["size"],
            group=node.node_type.value,
        )

    for edge in graph.edges:
        style = EDGE_STYLE.get(edge.relation, {"color": "#9CA3AF", "width": 1, "dashes": True})
        edge_label = EDGE_LABEL_MAP.get(edge.relation, edge.relation)
        net.add_edge(
            edge.source_id,
            edge.target_id,
            label=edge_label,
            title=_build_edge_tooltip(edge),
            color=style["color"],
            width=style["width"],
            dashes=style["dashes"],
        )

    return net

def save_pyvis_graph(graph: EvidenceGraph) -> str:
    """Save graph to HTML file and return path."""
    net = build_pyvis_graph(graph)
    temp_dir = tempfile.mkdtemp(prefix="remake_graph_")
    html_path = os.path.join(temp_dir, "graph.html")
    net.save_graph(html_path)
    try:
        with open(html_path, "r", encoding="utf-8") as fh:
            html = fh.read()
        stabilization_script = """
        <script>
        if (typeof network !== "undefined") {
          network.once("stabilizationIterationsDone", function () {
            network.setOptions({ physics: { enabled: false } });
          });
        }
        </script>
        """
        html = html.replace("</body>", stabilization_script + "\n</body>")
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(html)
    except Exception as exc:
        logger.debug("Could not inject graph stabilization script: %s", exc)
    return html_path

def _display_label(node) -> str:
    """Generate short display label for node."""
    if node.node_type == NodeType.MEDIA:
        return "media"
    if len(node.label) <= 35:
        return node.label
    return node.label[:32] + "…"

def _build_node_tooltip(node) -> str:
    """
    Generate human-readable tooltip for node.
    
    Rules:
    - Query node: "Search query: {query}"
    - Record node: title, source, object/page link, retrieval explanation, metadata preview
    - Media node: multimedia preview/link, record title
    - Claim node: field label, value, source record, source link
    
    Hide raw keys (claim_id, record_key, payload, object_id) unless DEBUG_UI is True.
    """
    parts = []
    
    try:
        if node.node_type == NodeType.QUERY:
            query = node.payload.get("query", node.label)
            return f"<b>Search Query:</b><br>{query}"
        
        elif node.node_type == NodeType.RECORD:
            # Title
            title = node.payload.get("title", node.label)
            parts.append(f"<b>{title}</b>")
            
            # Source
            source = node.payload.get("source", "")
            if source:
                parts.append(f"<i>Source:</i> {source}")
            
            # Object/page link
            source_url = node.payload.get("source_url", "")
            if source_url:
                parts.append(f"<i>Record:</i> <a href='{source_url}' target='_blank'>View original</a>")
            
            # Retrieval explanation
            retrieval_class = node.payload.get("retrieval_class", "")
            if retrieval_class:
                explanation = _retrieval_explanation(retrieval_class)
                parts.append(f"<i>Match type:</i> {explanation}")
            
            # Metadata preview (selected fields)
            metadata = node.payload.get("metadata", {})
            if isinstance(metadata, dict):
                preview_fields = ["maker", "date", "object_name", "description"]
                for field in preview_fields:
                    if field in metadata and metadata[field]:
                        value = str(metadata[field])
                        if len(value) > 80:
                            value = value[:77] + "…"
                        parts.append(f"<i>{field}:</i> {value}")
            
            if DEBUG_UI:
                object_id = node.payload.get("object_id", "")
                if object_id:
                    parts.append(f"<small>[DEBUG] object_id: {object_id}</small>")
        
        elif node.node_type == NodeType.MEDIA:
            # Media preview
            image_url = node.payload.get("image_url", "")
            record_title = node.payload.get("record_title", "Media")
            
            if image_url:
                parts.append(f"<b>{record_title}</b>")
                # HTML img tag with limited dimensions
                parts.append(f"<img src='{image_url}' style='max-width: 200px; max-height: 200px; border: 1px solid #ccc;'>")
            else:
                parts.append(f"<b>{record_title}</b>")
                parts.append("<i>No media preview available</i>")
        
        elif node.node_type == NodeType.CLAIM:
            # Field name and value
            field = node.payload.get("field", "")
            value = node.payload.get("value", "")
            source_record = node.payload.get("source_record_title", "")
            source_link = node.payload.get("source_url", "")
            
            if field:
                parts.append(f"<b>{field}</b>")
            if value:
                parts.append(f"<i>Value:</i> {value}")
            if source_record:
                parts.append(f"<i>Source:</i> {source_record}")
            if source_link:
                parts.append(f"<a href='{source_link}' target='_blank'>View source</a>")
            
            if DEBUG_UI:
                claim_id = node.payload.get("claim_id", "")
                record_key = node.payload.get("record_key", "")
                if claim_id:
                    parts.append(f"<small>[DEBUG] claim_id: {claim_id}</small>")
                if record_key:
                    parts.append(f"<small>[DEBUG] record_key: {record_key}</small>")
        
        else:
            # Generic fallback
            parts.append(f"<b>{node.label}</b>")
            parts.append(f"<i>Type:</i> {node.node_type.value}")
            
            # Show selected payload items
            for key, value in list(node.payload.items())[:5]:
                if key in ("claim_id", "record_key", "payload", "object_id") and not DEBUG_UI:
                    continue
                if value in (None, "", [], {}):
                    continue
                value_str = str(value)
                if len(value_str) > 60:
                    value_str = value_str[:57] + "…"
                parts.append(f"<i>{key}:</i> {value_str}")
    
    except Exception as e:
        logger.debug(f"Tooltip generation error: {e}")
        parts = [f"<b>{node.label}</b>", f"Type: {node.node_type.value}"]
    
    return "<br>".join(parts)

def _build_edge_tooltip(edge) -> str:
    """
    Generate human-readable tooltip for edge.
    
    Show:
    - Relation name and plain-language explanation
    - Weight/strength if relevant
    - Evidence summary
    """
    parts = []
    
    try:
        relation_display = EDGE_LABEL_MAP.get(edge.relation, edge.relation)
        parts.append(f"<b>{relation_display}</b>")
        
        # Plain-language explanation
        explanation = retrieval_edge_meaning(edge.relation)
        if explanation:
            parts.append(f"<i>{explanation}</i>")
        
        # Weight
        if edge.weight and edge.weight != 1.0:
            parts.append(f"<i>Strength:</i> {edge.weight:.2f}")
        
        # Evidence summary
        evidence = edge.evidence or {}
        if isinstance(evidence, dict):
            for key in ["similarity_score", "match_fields", "evidence_summary"]:
                if key in evidence and evidence[key]:
                    value = evidence[key]
                    if isinstance(value, (int, float)):
                        parts.append(f"<i>{key}:</i> {value:.2f}" if isinstance(value, float) else f"<i>{key}:</i> {value}")
                    else:
                        value_str = str(value)
                        if len(value_str) > 100:
                            value_str = value_str[:97] + "…"
                        parts.append(f"<i>{key}:</i> {value_str}")
        
        if not parts:
            parts.append(f"<b>{edge.relation}</b>")
    
    except Exception as e:
        logger.debug(f"Edge tooltip generation error: {e}")
        parts = [f"<b>{edge.relation}</b>"]
    
    return "<br>".join(parts)

def _retrieval_explanation(retrieval_class: str) -> str:
    """Provide human-readable explanation for retrieval class."""
    explanations = {
        "exact_title_match": "Exact title match with query",
        "title_match": "Title contains query",
        "alias_match": "Alias or alternative name matches",
        "description_match": "Query found in description",
        "subject_match": "Query found in subject tags",
        "retrieval_match": "Retrieved from source search",
        "non_api_curated": "From curated collection",
        "manual_user_added": "User-added record",
    }
    return explanations.get(retrieval_class, retrieval_class)

# Import logger for error handling
import logging
logger = logging.getLogger(__name__)
