from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional
import json


class NodeType(Enum):
    QUERY = "query"
    RECORD = "record"
    CONCEPT = "concept"
    MEDIA = "media"
    CLAIM = "claim"
    SEMANTIC_OBJECT = "semantic_object"
    SEMANTIC_ACTOR = "semantic_actor"
    SEMANTIC_TYPE = "semantic_type"
    SEMANTIC_EVENT = "semantic_event"
    SEMANTIC_TIME = "semantic_time"
    SEMANTIC_MATERIAL = "semantic_material"


class UncertaintyType(Enum):
    MISSINGNESS = "missingness"
    TEXTUAL_DISAGREEMENT = "textual_disagreement"
    MULTIMODAL_CONSISTENCY = "multimodal_consistency"


class IdentityStatus(Enum):
    NO_IDENTITY_CLAIM = "no_identity_claim"
    CANDIDATE_MATCH = "candidate_match"
    USER_ASSERTED_SAME_OBJECT = "user_asserted_same_object"
    SOURCE_ASSERTED_SAME_OBJECT = "source_asserted_same_object"


@dataclass
class SourceSchema:
    source: str
    schema_name: str
    fields: List[str]
    field_groups: Dict[str, str] = field(default_factory=dict)


@dataclass
class Record:
    object_id: str
    source: str
    title: str
    metadata: Dict[str, Any]
    image_url: Optional[str] = None
    source_url: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)
    retrieval_class: str = "retrieval_match"
    is_semantic_anchor: bool = False
    source_schema: Optional[Any] = None
    source_type: Optional[str] = None
    evidence_spans: list = field(default_factory=list)
    local_image_path: Optional[str] = None
    human_validations: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.object_id}"

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["key"] = self.key
        return data


@dataclass
class GraphNode:
    node_id: str
    node_type: NodeType
    label: str
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "label": self.label,
            "payload": self.payload,
        }


@dataclass
class GraphEdge:
    source_id: str
    target_id: str
    relation: str
    weight: float = 1.0
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation,
            "weight": self.weight,
            "evidence": self.evidence,
        }


@dataclass
class EvidenceGraph:
    query: str
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)
    records: List[Record] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "records": [r.to_dict() for r in self.records],
        }


@dataclass
class EvidenceAnswer:
    question_id: str
    label: str
    items: List[Dict[str, Any]]
    notes: List[str] = field(default_factory=list)


@dataclass
class ExtractedClaim:
    claim_id: str
    record_key: str
    source_field: str
    claim_type: str
    raw_value: Any
    normalized_value: str
    evidence_span: str = ""
    confidence: float = 0.7
    extraction_method: str = "rules"
    requires_human_validation: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SignalResult:
    field: str
    uncertainty_type: UncertaintyType
    metric_name: str
    metric_value: float
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "uncertainty_type": self.uncertainty_type.value,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "details": self.details,
        }


@dataclass
class PromptResult:
    field: str
    uncertainty_type: UncertaintyType
    prompt: str
    reasoning: str = ""


@dataclass
class ValidatedFieldMapping:
    field_family: str
    source_fields: List[str]
    claim_type: str
    approved: bool = True
    notes: str = ""


@dataclass
class SchemaMatrix:
    sources: List[str]
    fields_by_source: Dict[str, List[str]]
    presence_rows: List[Dict[str, Any]]
    grouped_fields: Dict[str, Dict[str, List[str]]] = field(default_factory=dict)


@dataclass
class SemanticNodeSpec:
    label: str
    node_type: str
    crm_class: str
    crm_uri: Optional[str] = None
    mimo_uri: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SemanticEdgeSpec:
    source_role: str
    target_role: str
    predicate: str
    crm_property: Optional[str] = None
    crm_property_uri: Optional[str] = None
    notes: str = ""


@dataclass
class SemanticRecommendation:
    recommendation_id: str
    claim_id: str
    source_record_key: str
    pattern_id: str
    label: str
    confidence: float
    requires_human_validation: bool
    vocabulary_hint: str
    explanation: str
    nodes: List[SemanticNodeSpec]
    edges: List[SemanticEdgeSpec]
    provenance_note: str = ""
    action_label: str = ""
    plain_language_claim: str = ""
    scope: str = "record_local"
    provenance_record_key: str = ""
    source_field: str = ""
    risk_note: str = ""
    crm_pattern: List[str] = field(default_factory=list)
    preview_nodes: List[SemanticNodeSpec] = field(default_factory=list)
    preview_edges: List[SemanticEdgeSpec] = field(default_factory=list)


@dataclass
class SemanticGraph:
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)
    accepted_recommendation_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "accepted_recommendation_ids": self.accepted_recommendation_ids,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


@dataclass
class UncertaintyProfile:
    query: str
    selected_record_keys: List[str]
    comparison_table: Dict[str, Dict[str, Any]]
    all_fields: List[str]
    schema_matrix: Optional[SchemaMatrix] = None
    validated_mappings: List[ValidatedFieldMapping] = field(default_factory=list)
    extracted_claims: List[ExtractedClaim] = field(default_factory=list)
    signals: List[SignalResult] = field(default_factory=list)
    prompts: List[PromptResult] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)
