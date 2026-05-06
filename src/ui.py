"""Streamlit UI with validation-first workflow and proper graph rendering."""

from __future__ import annotations

import tempfile
import base64
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from pyvis.network import Network

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.evidence_queries import run_standard_evidence_queries
from src.graph_builder import add_record_to_graph, build_evidence_graph, retrieval_edge_meaning
from src.models import EvidenceGraph, ExtractedClaim, IdentityStatus, Record
from src.retrieval import search_all_sources
from src.export_semantic import semantic_graph_to_json, semantic_graph_to_turtle
from src.semantic_graph import (
    add_recommendation,
    create_empty_graph,
    merge_nodes,
    remove_recommendation,
    semantic_node_choices,
)
from src.semantic_recommendations import recommend_from_claims
from src.settings import DEBUG_UI, SHOW_DIRECT_EVIDENCE_TABLES, SOURCE_REGISTRY, STREAMLIT_PAGE_CONFIG
from src.sparql import (
    default_local_sparql_query,
    default_remote_sparql_query,
    query_remote_sparql_endpoint,
    run_local_sparql_query,
)
from src.uncertainty_profile import build_profile
from src.visualization import save_pyvis_graph

from src.signals import build_claim_family_table

st.set_page_config(**STREAMLIT_PAGE_CONFIG)


# -----------------------
# PAGE BEHAVIOR
# -----------------------

def _enable_document_scrolling_for_recording():
    """
    Let the browser document own vertical scrolling.

    Streamlit normally scrolls inside an app viewport. That looks fine while
    using the app, but browser/tab recording and auto-scroll tools often track
    only window/document scrolling, so the captured video can appear static.
    """
    st.markdown(
        """
        <style>
        html,
        body,
        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        section.main {
            height: auto !important;
            min-height: 100% !important;
            overflow-y: visible !important;
        }

        .stApp,
        [data-testid="stAppViewContainer"] {
            position: static !important;
        }

        [data-testid="stMain"] {
            overflow-x: hidden !important;
        }

        [data-testid="stMainBlockContainer"],
        .block-container {
            padding-bottom: 4rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# -----------------------
# STATE
# -----------------------

def _init_state():
    for key, default in {
        "graph": None,
        "ui_language": "English",
        "selected_records": [],
        "profile": None,
        "evidence_answers": None,
        "validated_claims": None,
        "validated_table": None,
        "validated_signals": None,
        "recommendations": None,
        "semantic_graph": create_empty_graph(),
        "identity_status": IdentityStatus.NO_IDENTITY_CLAIM.value,
        "recommendation_identity_status": None,
        "local_sparql_query": default_local_sparql_query(),
        "remote_sparql_query": default_remote_sparql_query(),
        "remote_sparql_endpoint": "",
        "manual_image_interpretations": {},
    }.items():
        if key not in st.session_state:
            st.session_state[key] = default


# -----------------------
# UTILS
# -----------------------

UI_TEXT = {
    "English": {
        "app_title": "DIMA — Data Inspection for Multimedia Artefacts",
        "intro": "**An Instrument Knowledge Workbench for Exploring Musical Cultural Heritage.** Search heterogeneous cultural heritage sources, inspect retrieved records, explore uncertainty across claims, and optionally add external or manual evidence.",
        "language": "Language",
        "search_query": "Search query",
        "search": "Search",
        "retrieved_header": "Retrieved Source Records",
        "retrieved_caption": "This graph shows the query, retrieved records, source pages, multimedia links, and unvalidated retrieval cues.",
        "add_evidence": "Add external or manual evidence",
        "add_evidence_caption": "Choose a source type, paste copied page text when useful, then review or fill the fields before adding the record.",
        "evidence_source": "Evidence source",
        "copied_text": "Copied page text",
        "copied_text_placeholder": "For Boalch or Philharmonie: open the record page, select the visible record text, copy it, and paste it here.",
        "parse_copied_text": "Parse copied text",
        "parse_warning": "Copied text could not be parsed reliably. Fill the fields manually below.",
        "parsed": "Parsed",
        "parsed_preview": "Parsed preview",
        "all_source_fields": "All parsed source-specific fields",
        "add_parsed": "Add parsed record to record set",
        "added": "Added",
        "title": "Title",
        "source_label": "Source label",
        "source_url": "Source URL",
        "maker": "Maker",
        "date": "Date",
        "object_type": "Object/Type",
        "location": "Location/Collection",
        "materials": "Materials",
        "inventory": "Inventory number",
        "description": "Description",
        "notes": "Notes",
        "upload_image": "Upload image (optional)",
        "upload_scan": "Upload scanned source image (optional)",
        "add_record": "Add evidence record",
        "select_records": "Select records to consider",
        "select_records_caption": "Choose records only after search and optional added evidence. Selection means consider these records, not merge these records.",
        "compare_record": "Consider this record",
        "use_selected": "Use selected records",
        "open_original": "Open original record",
        "raw_spans": "Raw snippets / evidence spans:",
        "no_records_selected": "No records selected yet.",
        "selected_records": "Selected Records",
        "source": "Source",
        "metadata": "Metadata",
        "retrieved_as": "Retrieved as",
        "visual_indexing": "Visual indexing",
        "visual_indexing_caption": "Run zero-shot image classification for this record. Results are proposed evidence and must be reviewed before they enter the claim list.",
        "run_visual_indexing": "Run visual indexing",
        "visual_indexing_spinner": "Running zero-shot visual indexing...",
        "visual_indexing_success": "Visual indexing completed. Review the proposed visual observations below.",
        "accepted_visual_labels": "Accepted visual labels",
        "human_decision": "Human decision",
        "save_visual_indexing_review": "Save visual indexing review",
        "saved_visual_indexing_review": "Saved visual indexing review.",
        "proposed_image_observations": "Proposed image-derived observations",
        "edit_proposed_caption": "Edit proposed caption",
        "save_image_observation_review": "Save image observation review",
        "saved_image_observation_review": "Saved review for proposed image observations.",
        "image_interpretation_stored": "Image interpretation was stored as proposed evidence. Review it before treating it as a claim.",
        "decision_accept": "Accept",
        "decision_reject": "Reject",
        "decision_unsure": "Unsure",
        "claim_review": "Claim Review",
        "claim_review_caption": "Review extracted claims from selected records. Accept, reject, edit, or leave claims marked unsure.",
        "claim_review_action_hint": "Editable review cells: Human decision, Edit value, Notes.",
        "compare_selected": "Consider selected records",
        "semantic_workspace": "Semantic Workspace Graph",
        "semantic_proposals": "Semantic modeling proposals",
        "no_proposals": "No proposals yet.",
        "added_to_graph": "Added to semantic graph",
        "removed_from_graph": "Removed from semantic graph",
        "accept_graph": "Accept -> Graph",
        "remove_graph": "Remove from graph",
        "scope": "Scope",
        "evidence": "Evidence",
        "source_field": "Source field",
        "risk_note": "Risk note",
        "technical_crm": "Technical CRM mapping",
        "confidence": "Confidence",
        "vocabulary_hint": "Vocabulary hint",
        "preview_nodes": "Preview nodes",
        "preview_edges": "Preview edges",
        "identity_status": "Identity status",
        "relationship_records": "Relationship among selected records",
        "identity_effect": "This changes only the generated semantic proposals: without asserted identity, object and event nodes remain record-specific; with asserted identity, proposals can use shared object/event nodes while keeping source provenance.",
        "graph_empty": "Graph is empty.",
        "merge_nodes": "Merge nodes",
        "merge_need_two": "At least two semantic nodes are needed before merging.",
        "merge_source_node": "Merge source node",
        "merge_target_node": "Into target node",
        "merge_selected_nodes": "Merge selected nodes",
        "merged_nodes": "Merged nodes in the semantic graph.",
        "export_semantic_graph": "Export semantic graph",
        "download_semantic_json": "Download Semantic Graph (JSON)",
        "download_semantic_turtle": "Download Semantic Graph (Turtle)",
        "preview_turtle": "Preview Turtle",
        "export_analysis_context": "Export analysis context",
        "export_analysis_caption": "Export records, claims, and uncertainty signals as JSON",
        "download_analysis_json": "Download Analysis (JSON)",
        "preview_analysis": "Preview Analysis",
        "sparql_local_query": "Query the in-session semantic graph",
        "run_local_sparql": "Run local SPARQL",
        "local_sparql_no_rows": "The local SPARQL query returned no rows.",
        "local_sparql_unavailable": "Local SPARQL is unavailable right now",
        "install_rdflib": "Install `rdflib` to enable in-app local SPARQL querying.",
        "local_sparql_failed": "Local SPARQL query failed",
        "remote_sparql_endpoint": "Remote SPARQL endpoint",
        "endpoint_url": "Endpoint URL",
        "remote_select_query": "Remote SELECT query",
        "run_remote_sparql": "Run remote SPARQL",
        "enter_sparql_endpoint": "Enter a SPARQL endpoint URL first.",
        "remote_sparql_no_rows": "The remote SPARQL query returned no rows.",
        "remote_sparql_failed": "Remote SPARQL query failed",
        "direct_evidence": "Direct evidence",
        "build_profile": "Build profile",
        "apply_review": "Apply review",
    },
    "Italiano": {
        "app_title": "DIMA — Data Inspection for Multimedia Artefacts",
        "intro": "**Un banco di lavoro per la conoscenza degli strumenti musicali, pensato per esplorare il patrimonio culturale musicale.** Cerca in fonti eterogenee del patrimonio culturale, esamina i record recuperati, esplora l’incertezza nelle affermazioni e aggiungi eventuali evidenze esterne o manuali.",
        "language": "Lingua",
        "search_query": "Query di ricerca",
        "search": "Cerca",
        "retrieved_header": "Fonti recuperate",
        "retrieved_caption": "Questo grafo mostra la query, i record recuperati, le pagine fonte, i collegamenti multimediali e gli indizi di recupero non validati.",
        "add_evidence": "Aggiungi evidenza esterna o manuale",
        "add_evidence_caption": "Scegli il tipo di fonte, incolla il testo copiato dalla pagina se utile, poi controlla o compila i campi prima di aggiungere il record.",
        "evidence_source": "Fonte dell’evidenza",
        "copied_text": "Testo copiato dalla pagina",
        "copied_text_placeholder": "Per Boalch o Philharmonie: apri la pagina del record, seleziona il testo visibile del record, copialo e incollalo qui.",
        "parse_copied_text": "Analizza testo copiato",
        "parse_warning": "Il testo copiato non è stato interpretato in modo affidabile. Compila i campi manualmente qui sotto.",
        "parsed": "Interpretato",
        "parsed_preview": "Anteprima interpretata",
        "all_source_fields": "Tutti i campi specifici della fonte",
        "add_parsed": "Aggiungi record interpretato all’insieme",
        "added": "Aggiunto",
        "title": "Titolo",
        "source_label": "Etichetta della fonte",
        "source_url": "URL della fonte",
        "maker": "Autore / costruttore",
        "date": "Data",
        "object_type": "Oggetto / tipo",
        "location": "Luogo / collezione",
        "materials": "Materiali",
        "inventory": "Numero d’inventario",
        "description": "Descrizione",
        "notes": "Note",
        "upload_image": "Carica immagine (opzionale)",
        "upload_scan": "Carica scansione della fonte (opzionale)",
        "add_record": "Aggiungi record di evidenza",
        "select_records": "Seleziona record da considerare",
        "select_records_caption": "Scegli i record dopo la ricerca e dopo eventuali evidenze aggiunte. La selezione significa considerare questi record, non unirli.",
        "compare_record": "Considera questo record",
        "use_selected": "Usa i record selezionati",
        "open_original": "Apri record originale",
        "raw_spans": "Estratti grezzi / passi di evidenza:",
        "no_records_selected": "Nessun record selezionato.",
        "selected_records": "Record selezionati",
        "source": "Fonte",
        "metadata": "Metadati",
        "retrieved_as": "Recuperato come",
        "visual_indexing": "Indicizzazione visiva",
        "visual_indexing_caption": "Esegui una classificazione zero-shot dell’immagine per questo record. I risultati sono evidenze proposte e devono essere rivisti prima di entrare nella lista delle affermazioni.",
        "run_visual_indexing": "Esegui indicizzazione visiva",
        "visual_indexing_spinner": "Indicizzazione visiva zero-shot in corso...",
        "visual_indexing_success": "Indicizzazione visiva completata. Rivedi le osservazioni visive proposte qui sotto.",
        "accepted_visual_labels": "Etichette visive accettate",
        "human_decision": "Decisione umana",
        "save_visual_indexing_review": "Salva revisione dell’indicizzazione visiva",
        "saved_visual_indexing_review": "Revisione dell’indicizzazione visiva salvata.",
        "proposed_image_observations": "Osservazioni proposte derivate dall’immagine",
        "edit_proposed_caption": "Modifica didascalia proposta",
        "save_image_observation_review": "Salva revisione delle osservazioni dall’immagine",
        "saved_image_observation_review": "Revisione delle osservazioni proposte salvata.",
        "image_interpretation_stored": "L’interpretazione dell’immagine è stata salvata come evidenza proposta. Rivedila prima di trattarla come affermazione.",
        "decision_accept": "Accetta",
        "decision_reject": "Rifiuta",
        "decision_unsure": "Incerto",
        "claim_review": "Revisione delle affermazioni",
        "claim_review_caption": "Rivedi le affermazioni estratte dai record selezionati. Accetta, rifiuta, modifica o lascia come incerto.",
        "claim_review_action_hint": "Celle modificabili per la revisione: Decisione umana, Modifica valore, Note.",
        "compare_selected": "Considera i record selezionati",
        "semantic_workspace": "Grafo semantico di lavoro",
        "semantic_proposals": "Proposte di modellazione semantica",
        "no_proposals": "Nessuna proposta.",
        "added_to_graph": "Aggiunta al grafo semantico",
        "removed_from_graph": "Rimossa dal grafo semantico",
        "accept_graph": "Accetta -> Grafo",
        "remove_graph": "Rimuovi dal grafo",
        "scope": "Ambito",
        "evidence": "Evidenza",
        "source_field": "Campo della fonte",
        "risk_note": "Nota di cautela",
        "technical_crm": "Mappatura tecnica CRM",
        "confidence": "Confidenza",
        "vocabulary_hint": "Suggerimento di vocabolario",
        "preview_nodes": "Anteprima nodi",
        "preview_edges": "Anteprima archi",
        "identity_status": "Stato di identità",
        "relationship_records": "Relazione tra i record selezionati",
        "identity_effect": "Questo cambia solo le proposte semantiche generate: senza identità asserita, i nodi oggetto ed evento restano specifici del record; con identità asserita, le proposte possono usare nodi oggetto/evento condivisi mantenendo la provenienza della fonte.",
        "graph_empty": "Il grafo è vuoto.",
        "merge_nodes": "Unisci nodi",
        "merge_need_two": "Servono almeno due nodi semantici prima di unirli.",
        "merge_source_node": "Nodo sorgente da unire",
        "merge_target_node": "Nel nodo di destinazione",
        "merge_selected_nodes": "Unisci nodi selezionati",
        "merged_nodes": "Nodi uniti nel grafo semantico.",
        "export_semantic_graph": "Esporta grafo semantico",
        "download_semantic_json": "Scarica grafo semantico (JSON)",
        "download_semantic_turtle": "Scarica grafo semantico (Turtle)",
        "preview_turtle": "Anteprima Turtle",
        "export_analysis_context": "Esporta contesto dell’analisi",
        "export_analysis_caption": "Esporta record, affermazioni e segnali di incertezza come JSON",
        "download_analysis_json": "Scarica analisi (JSON)",
        "preview_analysis": "Anteprima analisi",
        "sparql_local_query": "Interroga il grafo semantico della sessione",
        "run_local_sparql": "Esegui SPARQL locale",
        "local_sparql_no_rows": "La query SPARQL locale non ha restituito righe.",
        "local_sparql_unavailable": "SPARQL locale non è disponibile in questo momento",
        "install_rdflib": "Installa `rdflib` per abilitare le query SPARQL locali nell’app.",
        "local_sparql_failed": "Query SPARQL locale non riuscita",
        "remote_sparql_endpoint": "Endpoint SPARQL remoto",
        "endpoint_url": "URL dell’endpoint",
        "remote_select_query": "Query SELECT remota",
        "run_remote_sparql": "Esegui SPARQL remoto",
        "enter_sparql_endpoint": "Inserisci prima l’URL di un endpoint SPARQL.",
        "remote_sparql_no_rows": "La query SPARQL remota non ha restituito righe.",
        "remote_sparql_failed": "Query SPARQL remota non riuscita",
        "direct_evidence": "Evidenza diretta",
        "build_profile": "Costruisci profilo",
        "apply_review": "Applica revisione",
    },
}


def t(key: str) -> str:
    language = st.session_state.get("ui_language", "English")
    return UI_TEXT.get(language, UI_TEXT["English"]).get(key, UI_TEXT["English"].get(key, key))

def _sanitize_rows(rows):
    clean = []
    for row in rows:
        new = {}
        for k, v in row.items():
            if v is None:
                new[k] = ""
            elif isinstance(v, (list, tuple, set)):
                new[k] = " | ".join(str(x) for x in v)
            elif isinstance(v, dict):
                new[k] = str(v)
            else:
                new[k] = v
        clean.append(new)
    return clean


def render_selected_records(records):
    """
    Render selected records with full metadata, images, and links.
    """
    if not records:
        st.info(t("no_records_selected"))
        return
    
    st.subheader(f"{t('selected_records')} ({len(records)})")
    
    for i, record in enumerate(records):
        source_info = SOURCE_REGISTRY.get(record.source, {})
        source_label = record.metadata.get("source_label") if record.source == "manual" else source_info.get("label")
        source_label = source_label or record.source
        with st.expander(f"{source_label} — {record.title}", expanded=(i == 0)):
            col1, col2 = st.columns([3, 1])
            
            with col1:
                # Source and key metadata
                st.markdown(f"**{t('source')}:** {source_label}")
                if record.source_url:
                    st.markdown(f"**[{t('open_original')} ->]({record.source_url})**")
                    st.caption(record.source_url)
                
                # Image thumbnail if available
                if record.image_url:
                    st.image(record.image_url, width=200, caption=record.title)
                elif record.local_image_path:
                    st.image(record.local_image_path, width=200, caption=record.title)
                
                # Metadata fields
                if record.metadata:
                    st.markdown(f"**{t('metadata')}:**")
                    for field, value in record.metadata.items():
                        if value and field != "source_specific":
                            st.write(f"• **{field}:** {value}")
                
                if record.evidence_spans:
                    with st.expander(t("raw_spans")):
                        for span in record.evidence_spans:
                            st.write(span)
                elif record.raw:
                    snippets = []
                    for key in ("snippet", "summary", "search_result"):
                        value = record.raw.get(key)
                        if value:
                            snippets.append(str(value)[:800])
                    if snippets:
                        with st.expander(t("raw_spans")):
                            for snippet in snippets:
                                st.caption(snippet)
                
                # Retrieval explanation
                if record.retrieval_class:
                    from src.visualization import _retrieval_explanation
                    explanation = _retrieval_explanation(record.retrieval_class)
                    st.caption(f"{t('retrieved_as')}: {explanation}")
            
            with col2:
                if DEBUG_UI:
                    st.markdown("**[DEBUG]**")
                    st.write(f"object_id: {record.object_id}")
                    st.write(f"retrieval_class: {record.retrieval_class}")
                    if record.raw:
                        st.write(f"raw keys: {list(record.raw.keys())}")


def _confidence_explanation(claim: ExtractedClaim) -> str:
    if claim.extraction_method == "structured_field":
        return "Exact metadata field"
    if claim.extraction_method == "description_rule":
        return "Extracted from description"
    if claim.extraction_method == "image_interpretation":
        return "Inferred from image"
    if claim.extraction_method in {"visual_indexing", "visual_indexing_alignment"}:
        return "Zero-shot visual indexing"
    if claim.extraction_method == "manual_user_added":
        return "User-entered"
    if claim.confidence < 0.6:
        return "Low confidence extraction"
    return "Extracted from record metadata"


IDENTITY_STATUS_LABELS = {
    IdentityStatus.NO_IDENTITY_CLAIM.value: "No identity claim",
    IdentityStatus.CANDIDATE_MATCH.value: "Candidate match",
    IdentityStatus.USER_ASSERTED_SAME_OBJECT.value: "User asserted same object",
    IdentityStatus.SOURCE_ASSERTED_SAME_OBJECT.value: "Source asserted same object",
}

IDENTITY_STATUS_HELP = {
    IdentityStatus.NO_IDENTITY_CLAIM.value: "Selected records are treated as separate witnesses in a research set.",
    IdentityStatus.CANDIDATE_MATCH.value: "Selected records may describe the same object, but this is not asserted.",
    IdentityStatus.USER_ASSERTED_SAME_OBJECT.value: "The user asserts that the selected records describe the same object.",
    IdentityStatus.SOURCE_ASSERTED_SAME_OBJECT.value: "A source or authority asserts that the selected records describe the same object.",
}

def _identity_status() -> str:
    return st.session_state.get("identity_status", IdentityStatus.NO_IDENTITY_CLAIM.value)


def render_identity_status_control():
    st.subheader(t("identity_status"))
    status = st.selectbox(
        t("relationship_records"),
        options=[status.value for status in IdentityStatus],
        format_func=lambda value: IDENTITY_STATUS_LABELS.get(value, value),
        key="identity_status",
    )
    st.caption(t("identity_effect"))


def render_badges(*labels):
    badge_html = " ".join(
        f"<span style='display:inline-block;border:1px solid #d0d7de;border-radius:999px;"
        f"padding:2px 8px;margin:0 4px 6px 0;font-size:0.78rem;background:#f6f8fa;'>{_localize_badge(label)}</span>"
        for label in labels
        if label
    )
    if badge_html:
        st.markdown(badge_html, unsafe_allow_html=True)


BADGE_TRANSLATIONS = {
    "retrieved evidence": "evidenza recuperata",
    "extracted claim": "affermazione estratta",
    "proposed semantic assertion": "asserzione semantica proposta",
    "accepted semantic assertion": "asserzione semantica accettata",
    "record local": "locale al record",
    "asserted same object": "stesso oggetto asserito",
}

ACTION_TRANSLATIONS = {
    "Add maker as production claim": "Aggiungi l'autore come affermazione di produzione",
    "Add production date": "Aggiungi la data di produzione",
    "Add material as composition claim": "Aggiungi il materiale come affermazione di composizione",
    "Add object type as classification": "Aggiungi il tipo di oggetto come classificazione",
}

SCOPE_LABELS = {
    "English": {
        "record_local": "record local",
        "asserted_same_object": "asserted same object",
    },
    "Italiano": {
        "record_local": "locale al record",
        "asserted_same_object": "stesso oggetto asserito",
    },
}


def _proposal_value(rec):
    for node in getattr(rec, "nodes", []):
        if node.node_type not in {"semantic_object", "semantic_event"}:
            return node.label
    return ""


def _localize_badge(label: str) -> str:
    if st.session_state.get("ui_language") == "Italiano":
        return BADGE_TRANSLATIONS.get(label, label)
    return label


def _localize_scope(scope: str) -> str:
    language = st.session_state.get("ui_language", "English")
    return SCOPE_LABELS.get(language, SCOPE_LABELS["English"]).get(scope, scope.replace("_", " "))


def _localized_proposal_text(rec):
    language = st.session_state.get("ui_language", "English")
    action = getattr(rec, "action_label", "") or rec.label
    claim = getattr(rec, "plain_language_claim", "") or rec.explanation
    risk = getattr(rec, "risk_note", "")

    if language != "Italiano":
        return action, claim, risk

    value = _proposal_value(rec)
    action_it = ACTION_TRANSLATIONS.get(action, action)
    if rec.pattern_id == "crm_e12_production_maker":
        claim_it = f"Questo record afferma che l'oggetto e stato realizzato da '{value}'."
    elif rec.pattern_id == "crm_e12_timespan":
        claim_it = f"Questo record indica la data di produzione come '{value}'."
    elif rec.pattern_id == "crm_material":
        claim_it = f"Questo record afferma che l'oggetto e composto da '{value}'."
    elif rec.pattern_id == "crm_type_with_mimo_hint":
        claim_it = f"Questo record afferma che l'oggetto e classificato come '{value}'."
    else:
        claim_it = claim

    if getattr(rec, "scope", "record_local") == "asserted_same_object":
        risk_it = "Lo stato di identita permette un'asserzione a livello di oggetto, mantenendo la provenienza del record fonte."
    else:
        risk_it = "Non applicare questa affermazione ad altri record selezionati se l'identita non e asserita."
    return action_it, claim_it, risk_it


def _claims_to_df(claims, records_by_key=None):
    """
    Convert ExtractedClaim objects to a user-facing review table while preserving
    internal IDs in hidden columns for round-tripping.
    """
    records_by_key = records_by_key or {}
    rows = []
    for c in claims:
        record = records_by_key.get(c.record_key)
        source_info = SOURCE_REGISTRY.get(record.source if record else "", {})
        source_label = None
        if record:
            source_label = record.metadata.get("source_label") if record.source == "manual" else source_info.get("label")
        source_label = source_label or (record.source if record else c.record_key.split(":")[0])
        source_url = record.source_url if record else ""
        excerpt = c.evidence_span or c.normalized_value
        if len(str(excerpt)) > 180:
            excerpt = str(excerpt)[:177] + "..."
        row = {
            "Field": c.claim_type or c.source_field or "unknown",
            "Extracted claim": c.normalized_value,
            "Source": source_label,
            "Original record": source_url,
            "Where found": f"{c.source_field or 'record'}: {excerpt}",
            "Human decision": "Unsure",
            "Edit value": c.normalized_value,
            "Notes": "",
            "_confidence_explanation": _confidence_explanation(c),
            "claim_id": c.claim_id,
            "record_key": c.record_key,
            "source_field": c.source_field,
            "claim_type": c.claim_type,
            "internal confidence": c.confidence,
            "raw evidence_span": c.evidence_span,
        }
        rows.append(row)
    return pd.DataFrame(rows)


def _df_to_claims(df):
    """Convert edited DataFrame back to ExtractedClaim objects."""
    claims = []
    for _, r in df.iterrows():
        if r.get("Human decision") == "Reject":
            continue
        
        # Determine confidence level from decision
        decision = r.get("Human decision", "Unsure")
        confidence = 0.8 if decision == "Accept" else (0.2 if decision == "Reject" else 0.5)
        value = r.get("Edit value") or r.get("Extracted claim") or ""
        
        claims.append(
            ExtractedClaim(
                claim_id=r.get("claim_id", ""),
                record_key=r.get("record_key", ""),
                source_field=r.get("source_field") or r.get("Field", ""),
                claim_type=r.get("claim_type", "extracted"),
                raw_value=value,
                normalized_value=value,
                confidence=float(confidence),
                evidence_span=r.get("raw evidence_span", ""),
                extraction_method="validated",
                requires_human_validation=False,
            )
        )
    return claims


def _claim_column_config():
    if st.session_state.get("ui_language") == "Italiano":
        return {
            "Field": st.column_config.TextColumn("Campo"),
            "Extracted claim": st.column_config.TextColumn("Affermazione estratta"),
            "Source": st.column_config.TextColumn("Fonte"),
            "Original record": st.column_config.LinkColumn("Record originale", display_text="Apri record originale"),
            "Where found": st.column_config.TextColumn("Dove è stato trovato"),
            "Human decision": st.column_config.SelectboxColumn(
                "Modifica: decisione umana",
                options=["Accept", "Reject", "Unsure"],
                required=True,
                help="Cella modificabile.",
            ),
            "Edit value": st.column_config.TextColumn("Modifica: valore", help="Cella modificabile."),
            "Notes": st.column_config.TextColumn("Modifica: note", help="Cella modificabile."),
        }
    return {
        "Original record": st.column_config.LinkColumn("Original record", display_text="Open original record"),
        "Human decision": st.column_config.SelectboxColumn(
            "Edit: Human decision",
            options=["Accept", "Reject", "Unsure"],
            required=True,
            help="Editable review cell.",
        ),
        "Edit value": st.column_config.TextColumn("Edit: value", help="Editable review cell."),
        "Notes": st.column_config.TextColumn("Edit: notes", help="Editable review cell."),
    }


def _uploaded_image_to_data_url(uploaded_file, local_image_path: str) -> str:
    suffix = Path(local_image_path).suffix.lower()
    media_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(suffix, "image/png")
    data = uploaded_file.getvalue()
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def _records_with_images(records):
    return [record for record in records if record.image_url or record.local_image_path]


def _visual_review_label(label_result: dict) -> str:
    value = label_result.get("claim_value") or label_result.get("label") or "visual observation"
    score = float(label_result.get("score") or 0.0)
    return f"{value} ({score:.2f})"


def _decision_label(decision: str) -> str:
    labels = {
        "Accept": t("decision_accept"),
        "Reject": t("decision_reject"),
        "Unsure": t("decision_unsure"),
    }
    return labels.get(decision, decision)


def render_record_visual_indexing(record):
    if not (record.image_url or record.local_image_path):
        return

    st.markdown(f"**{t('visual_indexing')}**")
    st.caption(t("visual_indexing_caption"))
    if st.button(t("run_visual_indexing"), key=f"run_visual_indexing_{record.key}"):
        from src.image_interpretation import index_record_visual_evidence

        with st.spinner(t("visual_indexing_spinner")):
            index_record_visual_evidence(record)
            record.human_validations.setdefault("visual_indexing", {})
            record.human_validations["visual_indexing"].setdefault("decision", "pending")
        st.session_state.profile = None
        st.session_state.validated_claims = None
        st.session_state.validated_table = None
        st.session_state.recommendations = None
        st.success(t("visual_indexing_success"))
        st.rerun()

    if not (isinstance(record.raw, dict) and record.raw.get("visual_indexing")):
        return

    visual_indexing = record.raw.get("visual_indexing", {})
    alignment = record.raw.get("image_text_alignment", {})
    st.json({
        "primary_label": visual_indexing.get("primary_label"),
        "primary_score": visual_indexing.get("primary_score"),
        "top_labels": visual_indexing.get("top_labels"),
        "image_text_alignment": {
            "overall_alignment": alignment.get("overall_alignment"),
            "alignment_score": alignment.get("alignment_score"),
            "supports": alignment.get("supports"),
            "conflicts": alignment.get("conflicts"),
            "unmentioned_visual_observations": alignment.get("unmentioned_visual_observations"),
        },
        "model": visual_indexing.get("model"),
        "error": visual_indexing.get("error"),
    })
    label_options = visual_indexing.get("top_labels") or []
    default_label_indexes = list(range(min(2, len(label_options)))) if visual_indexing.get("success") else []
    accepted_label_indexes = st.multiselect(
        t("accepted_visual_labels"),
        options=list(range(len(label_options))),
        default=default_label_indexes,
        format_func=lambda idx: _visual_review_label(label_options[idx]),
        key=f"visual_labels_{record.key}",
    )
    accepted_labels = [label_options[idx] for idx in accepted_label_indexes]
    decision = st.radio(
        t("human_decision"),
        ["Unsure", "Accept", "Reject"],
        key=f"visual_index_decision_{record.key}",
        horizontal=True,
        format_func=_decision_label,
    )
    note = st.text_area(t("notes"), key=f"visual_index_note_{record.key}")
    if st.button(t("save_visual_indexing_review"), key=f"save_visual_index_review_{record.key}"):
        record.human_validations["visual_indexing"] = {
            "decision": decision,
            "accepted_labels": accepted_labels,
            "note": note,
        }
        st.session_state.profile = None
        st.session_state.validated_claims = None
        st.session_state.validated_table = None
        st.session_state.recommendations = None
        st.success(t("saved_visual_indexing_review"))


def _non_api_source_schema(source: str):
    from src.non_api_retrieval import BOALCH_SCHEMA, PHILHARMONIE_SCHEMA

    if source == "boalch":
        return BOALCH_SCHEMA
    return PHILHARMONIE_SCHEMA


def _non_api_search_links(source: str, query: str) -> list[tuple[str, str]]:
    is_it = st.session_state.get("ui_language") == "Italiano"
    if source == "boalch":
        return [
            ("Apri Boalch-Mould Online" if is_it else "Open Boalch-Mould Online", "https://www.boalch.org/"),
        ]
    return [
        (
            "Apri le collezioni della Philharmonie" if is_it else "Open Philharmonie collections",
            "https://collectionsdumusee.philharmoniedeparis.fr/",
        ),
    ]


def _record_matches_query(record: Record, query: str) -> bool:
    q = (query or "").strip().lower()
    if not q:
        return True
    haystack = " ".join(
        str(value)
        for value in [record.title, record.source_url, *record.metadata.values()]
        if value
    ).lower()
    return q in haystack


def _source_object_id(source_url: str, title: str, fallback_prefix: str) -> str:
    if source_url:
        cleaned = source_url.rstrip("/").split("/")[-1].strip()
        if cleaned:
            return cleaned
    safe_title = "".join(ch if ch.isalnum() else "_" for ch in (title or "record").lower()).strip("_")
    return f"{fallback_prefix}_{safe_title or 'record'}"


def _source_options() -> list[str]:
    return ["manual", "boalch", "philharmonie"]


def _source_label(source: str) -> str:
    if st.session_state.get("ui_language") == "Italiano":
        italian_labels = {
            "manual": "Record manuale / esterno",
            "boalch": "Boalch–Mould Online",
            "philharmonie": "Collezioni del Museo della Philharmonie de Paris",
        }
        if source in italian_labels:
            return italian_labels[source]
    return SOURCE_REGISTRY.get(source, {}).get("label", source)


def render_record_selector():
    st.subheader(t("select_records"))
    st.caption(t("select_records_caption"))
    selected = []
    for r in st.session_state.graph.records:
        source_info = SOURCE_REGISTRY.get(r.source, {})
        source_label = r.metadata.get("source_label") if r.source == "manual" else source_info.get("label")
        source_label = source_label or r.source
        with st.expander(f"{source_label} — {r.title}", expanded=False):
            considered = st.checkbox(t("compare_record"), key=r.key)
            if considered:
                selected.append(r)
            col_a, col_b = st.columns([3, 1])
            with col_a:
                if r.source_url:
                    st.markdown(f"**[{t('open_original')}]({r.source_url})**")
                    st.caption(r.source_url)
                explanation = retrieval_edge_meaning(r.retrieval_class)
                st.caption(explanation)
                for field, value in r.metadata.items():
                    if field != "source_specific" and value:
                        st.write(f"**{field}:** {value}")
                if r.evidence_spans:
                    st.write(f"**{t('raw_spans')}**")
                    for span in r.evidence_spans:
                        st.caption(str(span)[:500])
            with col_b:
                if r.image_url:
                    st.image(r.image_url, width=160)
                elif r.local_image_path:
                    st.image(r.local_image_path, width=160)
                if DEBUG_UI:
                    st.caption(f"object_id: {r.object_id}")
            if considered:
                render_record_visual_indexing(r)

    if st.button(t("use_selected")):
        st.session_state.selected_records = selected
        st.session_state.evidence_answers = run_standard_evidence_queries(selected)


def _make_user_added_record(
    source: str,
    title: str,
    source_url: str,
    maker: str,
    date: str,
    object_name: str,
    location: str,
    materials: str,
    inventory_number: str,
    description: str,
    notes: str,
    source_label: str,
    image_url: str | None = None,
    local_image_path: str | None = None,
    upload_metadata: dict | None = None,
) -> Record:
    is_manual = source == "manual"
    metadata = {
        "title": title,
        "maker": maker,
        "date": date,
        "object_name": object_name,
        "location": location,
        "materials": materials,
        "inventory_number": inventory_number,
        "description": description,
        "notes": notes,
    }
    if is_manual and source_label:
        metadata["source_label"] = source_label
    metadata = {k: v for k, v in metadata.items() if v}
    source_info = SOURCE_REGISTRY.get(source, SOURCE_REGISTRY["manual"])
    return Record(
        object_id=_source_object_id(source_url, title, source),
        source=source,
        title=title,
        metadata=metadata,
        image_url=image_url,
        source_url=source_url or None,
        raw={"user_added": True, "upload_metadata": upload_metadata or {}},
        retrieval_class="manual_user_added" if is_manual else "non_api_curated",
        is_semantic_anchor=False,
        source_type=source_info["type"],
        source_schema=None if is_manual else _non_api_source_schema(source),
        evidence_spans=[description] if description else [],
        local_image_path=local_image_path,
        human_validations={},
    )


# -----------------------
# GRAPH
# -----------------------

def render_graph(graph: EvidenceGraph):
    html_path = save_pyvis_graph(graph)
    st.iframe(Path(html_path), height=750)


def render_proposal_mini_graph(rec):
    net = Network(height="220px", width="100%", directed=True)
    net.set_options("""
    const options = {
      "physics": {"enabled": false},
      "layout": {"hierarchical": {"enabled": true, "direction": "LR", "sortMethod": "directed"}},
      "interaction": {"dragNodes": true, "dragView": false, "zoomView": false, "hover": true}
    }
    """)

    node_color = {
        "semantic_object": "#dbeafe",
        "semantic_actor": "#dcfce7",
        "semantic_type": "#fef3c7",
        "semantic_event": "#ede9fe",
        "semantic_time": "#e0f2fe",
        "semantic_material": "#fae8ff",
    }
    preview_nodes = getattr(rec, "preview_nodes", None) or rec.nodes
    preview_edges = getattr(rec, "preview_edges", None) or rec.edges

    for node in preview_nodes:
        net.add_node(
            node.label,
            label=node.label,
            title=f"{node.node_type}<br>{node.crm_class}",
            color=node_color.get(node.node_type, "#f6f8fa"),
        )
    for edge in preview_edges:
        net.add_edge(edge.source_role, edge.target_role, label=edge.predicate)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".html")
    net.save_graph(tmp.name)
    st.iframe(Path(tmp.name), height=240)


def render_recommendations(recommendations):
    st.header(t("semantic_proposals"))

    if not recommendations:
        st.info(t("no_proposals"))
        return

    added_recommendation_ids = {
        item.get("recommendation_id")
        for item in st.session_state.semantic_graph.provenance
        if item.get("recommendation_id")
    }

    for rec in recommendations:
        already_added = rec.recommendation_id in added_recommendation_ids
        with st.expander(f"{rec.label} ({rec.claim_id})", expanded=False):
            action_text, claim_text, _ = _localized_proposal_text(rec)
            if already_added:
                st.success(t("added_to_graph"))

            st.markdown(f"### {action_text}")
            st.write(claim_text)
            st.write(f"**{t('evidence')}:** {getattr(rec, 'provenance_record_key', '') or rec.source_record_key}")
            source_field = getattr(rec, "source_field", "")
            if source_field:
                st.caption(f"{t('source_field')}: {source_field}")
            st.caption(rec.provenance_note)

            with st.expander(t("technical_crm")):
                crm_pattern = getattr(rec, "crm_pattern", [])
                preview_nodes = getattr(rec, "preview_nodes", None) or rec.nodes
                preview_edges = getattr(rec, "preview_edges", None) or rec.edges
                if crm_pattern:
                    st.write("Pattern: " + " -> ".join(crm_pattern))
                st.write(f"{t('confidence')}: {rec.confidence:.2f}")
                st.write(f"{t('vocabulary_hint')}: {rec.vocabulary_hint}")
                st.markdown(f"#### {t('preview_nodes')}")
                st.dataframe(pd.DataFrame([vars(node) for node in preview_nodes]), width="stretch")
                st.markdown(f"#### {t('preview_edges')}")
                st.dataframe(pd.DataFrame([vars(edge) for edge in preview_edges]), width="stretch")

            if already_added:
                if st.button(
                    f"{t('remove_graph')} ({rec.recommendation_id})",
                    key=f"remove_{rec.recommendation_id}",
                ):
                    remove_recommendation(st.session_state.semantic_graph, rec.recommendation_id)
                    st.success(t("removed_from_graph"))
                    st.rerun()
            else:
                if st.button(
                    f"{t('accept_graph')} ({rec.recommendation_id})",
                    key=f"accept_{rec.recommendation_id}",
                ):
                    add_recommendation(st.session_state.semantic_graph, rec)
                    st.success(t("added_to_graph"))
                    st.rerun()


def render_semantic_graph(graph, show_header=True):
    if show_header:
        st.header(t("semantic_workspace"))

    if not graph.nodes:
        st.info(t("graph_empty"))
        return

    net = Network(height="600px", width="100%", directed=True)
    net.set_options("""
    const options = {
      "physics": {"enabled": false},
      "layout": {"improvedLayout": true, "randomSeed": 7},
      "interaction": {"dragNodes": true, "dragView": false, "zoomView": false, "hover": true}
    }
    """)

    for node in graph.nodes.values():
        title_parts = [node.crm_class]
        if node.crm_uri:
            title_parts.append(node.crm_uri)
        if node.mimo_uri:
            title_parts.append(node.mimo_uri)

        net.add_node(
            node.id,
            label=node.label,
            title="<br>".join(title_parts),
        )

    for edge in graph.edges:
        net.add_edge(
            edge.source,
            edge.target,
            label=edge.predicate,
            title=edge.crm_property_uri or edge.crm_property or edge.predicate,
        )

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".html")
    net.save_graph(tmp.name)
    st.iframe(Path(tmp.name), height=600)


def render_merge_controls(graph):
    st.subheader(t("merge_nodes"))

    choices = semantic_node_choices(graph)
    if len(choices) < 2:
        st.caption(t("merge_need_two"))
        return

    labels = {node_id: label for node_id, label in choices}
    node_ids = [node_id for node_id, _ in choices]

    source_node_id = st.selectbox(
        t("merge_source_node"),
        options=node_ids,
        format_func=lambda node_id: labels[node_id],
        key="merge_source_node_id",
    )
    target_node_id = st.selectbox(
        t("merge_target_node"),
        options=[node_id for node_id in node_ids if node_id != source_node_id],
        format_func=lambda node_id: labels[node_id],
        key="merge_target_node_id",
    )

    if st.button(t("merge_selected_nodes"), key="merge_semantic_nodes"):
        merge_nodes(graph, source_node_id, target_node_id)
        st.success(t("merged_nodes"))


def export_analysis_context(query: str, selected_records, validated_claims, signals, identity_status=None):
    """
    Export the full analysis context as JSON.
    Includes: query, selected records, claims, uncertainty signals, source types.
    """
    import json
    from datetime import datetime
    
    export_data = {
        "timestamp": datetime.now().isoformat(),
        "query": query,
        "identity_status": identity_status or _identity_status(),
        "selected_records": [],
        "manual_records": [],
        "validated_claims": [],
        "uncertainty_explanations": [],
    }
    
    # Export selected records
    if selected_records:
        for record in selected_records:
            record_dict = {
                "object_id": record.object_id,
                "source": record.source,
                "source_type": record.source_type,
                "retrieval_class": record.retrieval_class,
                "title": record.title,
                "source_url": record.source_url,
                "metadata": record.metadata,
                "image_url": record.image_url,
                "local_image_path": record.local_image_path,
                "evidence_spans": record.evidence_spans,
                "human_validations": record.human_validations,
                "image_interpretation": record.raw.get("image_interpretation") if isinstance(record.raw, dict) else None,
                "visual_indexing": record.raw.get("visual_indexing") if isinstance(record.raw, dict) else None,
                "image_text_alignment": record.raw.get("image_text_alignment") if isinstance(record.raw, dict) else None,
            }
            export_data["selected_records"].append(record_dict)
            if record.source == "manual":
                export_data["manual_records"].append(record_dict)
    
    # Export validated claims
    if validated_claims:
        for claim in validated_claims:
            claim_dict = {
                "claim_id": claim.claim_id,
                "source_record": claim.record_key,
                "field": claim.source_field,
                "value": claim.normalized_value,
                "confidence": claim.confidence,
                "evidence_span": claim.evidence_span,
            }
            export_data["validated_claims"].append(claim_dict)
    
    # Export uncertainty signals
    if signals:
        for signal in signals:
            signal_dict = signal.to_dict()
            export_data["uncertainty_explanations"].append(signal_dict)
    
    return json.dumps(export_data, indent=2, default=str)


def render_export_tools(graph, query="", selected_records=None, validated_claims=None, signals=None):
    """Render export options for semantic graph and analysis context."""
    st.subheader(t("export_semantic_graph"))

    json_payload = semantic_graph_to_json(graph)
    turtle_payload = semantic_graph_to_turtle(graph)

    st.download_button(
        t("download_semantic_json"),
        data=json_payload,
        file_name="semantic_graph.json",
        mime="application/json",
    )
    st.download_button(
        t("download_semantic_turtle"),
        data=turtle_payload,
        file_name="semantic_graph.ttl",
        mime="text/turtle",
    )

    with st.expander(t("preview_turtle")):
        st.code(turtle_payload, language="turtle")
    
    # Export analysis context
    st.subheader(t("export_analysis_context"))
    st.caption(t("export_analysis_caption"))
    
    analysis_json = export_analysis_context(query, selected_records, validated_claims, signals, identity_status=_identity_status())
    st.download_button(
        t("download_analysis_json"),
        data=analysis_json,
        file_name="analysis_context.json",
        mime="application/json",
    )
    
    with st.expander(t("preview_analysis")):
        st.json(analysis_json)


def render_sparql_tools(graph):
    st.subheader("SPARQL")

    local_query = st.text_area(
        t("sparql_local_query"),
        key="local_sparql_query",
        height=180,
    )
    if st.button(t("run_local_sparql"), key="run_local_sparql"):
        try:
            rows = run_local_sparql_query(graph, local_query)
            if rows:
                st.dataframe(pd.DataFrame(rows), width="stretch")
            else:
                st.info(t("local_sparql_no_rows"))
        except Exception as exc:
            message = str(exc)
            if "rdflib is required" in message:
                st.warning(f"{t('local_sparql_unavailable')}: {message}")
                st.caption(t("install_rdflib"))
            else:
                st.error(f"{t('local_sparql_failed')}: {message}")

    st.markdown(f"### {t('remote_sparql_endpoint')}")
    st.text_input(t("endpoint_url"), key="remote_sparql_endpoint")
    remote_query = st.text_area(
        t("remote_select_query"),
        key="remote_sparql_query",
        height=180,
    )
    if st.button(t("run_remote_sparql"), key="run_remote_sparql"):
        endpoint_url = st.session_state.remote_sparql_endpoint.strip()
        if not endpoint_url:
            st.warning(t("enter_sparql_endpoint"))
        else:
            try:
                rows = query_remote_sparql_endpoint(endpoint_url, remote_query)
                if rows:
                    st.dataframe(pd.DataFrame(rows), width="stretch")
                else:
                    st.info(t("remote_sparql_no_rows"))
            except Exception as exc:
                st.error(f"{t('remote_sparql_failed')}: {exc}")


# -----------------------
# MAIN
# -----------------------

def main():
    _init_state()
    _enable_document_scrolling_for_recording()

    st.sidebar.radio(
        "Language / Lingua",
        options=["English", "Italiano"],
        key="ui_language",
        horizontal=True,
    )

    st.title(t("app_title"))
    st.markdown(t("intro"))

    # SEARCH
    query = st.text_input(t("search_query"))

    if st.button(t("search")):
        results = search_all_sources(query, rows=5)
        graph = build_evidence_graph(query, results)
        st.session_state.graph = graph

    # GRAPH
    if st.session_state.graph:
        st.header(t("retrieved_header"))
        st.caption(t("retrieved_caption"))
        render_graph(st.session_state.graph)

    # ADD EXTERNAL / MANUAL / SOURCE-SPECIFIC RECORD
    if st.session_state.graph:
        st.subheader(t("add_evidence"))
        st.caption(t("add_evidence_caption"))

        evidence_source = st.selectbox(
            t("evidence_source"),
            options=_source_options(),
            format_func=_source_label,
            key="evidence_source",
        )
        if evidence_source != "manual":
            for label, url in _non_api_search_links(evidence_source, query):
                st.markdown(f"**[{label}]({url})**")

            st.caption(
                "Paste the visible record text copied from the catalogue page when it is useful. You can still fill or correct every field manually below."
                if st.session_state.get("ui_language") == "English"
                else "Incolla il testo visibile copiato dalla pagina del catalogo quando è utile. Puoi comunque compilare o correggere manualmente ogni campo qui sotto."
            )
            copied_page_text = st.text_area(
                t("copied_text"),
                placeholder=t("copied_text_placeholder"),
                key="evidence_copied_text",
                height=180,
            )
            if st.button(t("parse_copied_text"), key="parse_evidence_text"):
                from src.non_api_retrieval import parse_record_from_copied_text

                extracted_record = parse_record_from_copied_text(copied_page_text, evidence_source, None)
                if extracted_record:
                    st.session_state.extracted_non_api_record = extracted_record
                    st.success(f"{t('parsed')} {extracted_record.title}")
                else:
                    st.warning(t("parse_warning"))

        extracted_record = st.session_state.get("extracted_non_api_record")
        if extracted_record and extracted_record.source == evidence_source:
            with st.container(border=True):
                st.markdown(f"**{t('parsed_preview')}: {extracted_record.title}**")
                if extracted_record.source_url:
                    st.markdown(f"[{t('open_original')}]({extracted_record.source_url})")
                for field, value in extracted_record.metadata.items():
                    if field != "source_specific" and value:
                        st.write(f"**{field}:** {value}")
                with st.expander(t("all_source_fields")):
                    st.json(extracted_record.metadata.get("source_specific", {}))
                if st.button(t("add_parsed"), key="add_parsed_evidence_record"):
                    add_record_to_graph(st.session_state.graph, extracted_record)
                    st.success(f"{t('added')} {_source_label(evidence_source)} record: {extracted_record.title}")
                    del st.session_state.extracted_non_api_record
                    st.rerun()

        with st.form("external_evidence_form"):
            col1, col2 = st.columns(2)
            parsed_metadata = extracted_record.metadata if extracted_record and extracted_record.source == evidence_source else {}
            with col1:
                evidence_title = st.text_input(t("title"), value=parsed_metadata.get("title", ""), key="evidence_title")
                evidence_source_label = st.text_input(t("source_label"), value="manual", key="evidence_source_label", disabled=evidence_source != "manual")
                evidence_source_url = st.text_input(t("source_url"), value=(extracted_record.source_url if extracted_record and extracted_record.source_url else ""), key="evidence_source_url")
                evidence_maker = st.text_input(t("maker"), value=parsed_metadata.get("maker", ""), key="evidence_maker")
                evidence_date = st.text_input(t("date"), value=parsed_metadata.get("date", ""), key="evidence_date")
                evidence_object_name = st.text_input(t("object_type"), value=parsed_metadata.get("object_name", ""), key="evidence_object_name")
            with col2:
                evidence_location = st.text_input(t("location"), value=parsed_metadata.get("location") or parsed_metadata.get("collection", ""), key="evidence_location")
                evidence_materials = st.text_input(t("materials"), value=parsed_metadata.get("materials", ""), key="evidence_materials")
                evidence_inventory = st.text_input(t("inventory"), value=parsed_metadata.get("inventory_number", ""), key="evidence_inventory")
                evidence_description = st.text_area(t("description"), value=parsed_metadata.get("description", ""), key="evidence_description")
                evidence_notes = st.text_area(t("notes"), key="evidence_notes")
                evidence_image = st.file_uploader(t("upload_image"), type=["jpg", "jpeg", "png", "gif"], key="evidence_image")
                evidence_scan = st.file_uploader(t("upload_scan"), type=["jpg", "jpeg", "png", "gif", "pdf"], key="evidence_scan")

            submitted = st.form_submit_button(t("add_record"))

            if submitted and evidence_title:
                local_image_path = None
                image_url = None
                upload_metadata = {}
                if evidence_image:
                    temp_dir = tempfile.mkdtemp(prefix="remake_evidence_image_")
                    local_image_path = f"{temp_dir}/{evidence_image.name}"
                    with open(local_image_path, "wb") as f:
                        f.write(evidence_image.getbuffer())
                    image_url = _uploaded_image_to_data_url(evidence_image, local_image_path)
                    upload_metadata["image_upload"] = {
                        "filename": evidence_image.name,
                        "content_type": evidence_image.type,
                        "size": evidence_image.size,
                    }

                if evidence_scan:
                    temp_dir = tempfile.mkdtemp(prefix="remake_evidence_scan_")
                    local_scan_path = f"{temp_dir}/{evidence_scan.name}"
                    with open(local_scan_path, "wb") as f:
                        f.write(evidence_scan.getbuffer())
                    upload_metadata["scanned_source_upload"] = {
                        "filename": evidence_scan.name,
                        "content_type": evidence_scan.type,
                        "size": evidence_scan.size,
                        "local_path": local_scan_path,
                    }

                evidence_record = _make_user_added_record(
                    source=evidence_source,
                    title=evidence_title,
                    source_url=evidence_source_url,
                    maker=evidence_maker,
                    date=evidence_date,
                    object_name=evidence_object_name,
                    location=evidence_location,
                    materials=evidence_materials,
                    inventory_number=evidence_inventory,
                    description=evidence_description,
                    notes=evidence_notes,
                    source_label=evidence_source_label,
                    image_url=image_url,
                    local_image_path=local_image_path,
                    upload_metadata=upload_metadata,
                )

                if local_image_path:
                    from src.image_interpretation import interpret_record_image
                    interpretation = interpret_record_image(evidence_record)
                    evidence_record.raw["image_interpretation"] = interpretation
                    evidence_record.human_validations["image_interpretation"] = {
                        "decision": "pending",
                        "note": "Image-derived observations are proposed evidence only.",
                    }

                add_record_to_graph(st.session_state.graph, evidence_record)
                st.success(f"{t('added')} {_source_label(evidence_source)} record: {evidence_title}")
                if local_image_path:
                    st.info(t("image_interpretation_stored"))
                st.rerun()

        manual_records = [r for r in st.session_state.graph.records if r.source == "manual" and r.raw.get("image_interpretation")]
        if manual_records:
            st.markdown(f"#### {t('proposed_image_observations')}")
            for record in manual_records:
                interpretation = record.raw.get("image_interpretation", {})
                with st.expander(record.title):
                    st.json({
                        "visible_object_type": interpretation.get("visible_object_type"),
                        "visible_materials": interpretation.get("visible_materials"),
                        "visible_features": interpretation.get("visible_features"),
                        "caption": interpretation.get("caption"),
                        "confidence_note": interpretation.get("confidence_note"),
                    })
                    decision = st.radio(
                        t("human_decision"),
                        ["Unsure", "Accept", "Reject"],
                        key=f"manual_image_decision_{record.key}",
                        horizontal=True,
                        format_func=_decision_label,
                    )
                    edited_caption = st.text_input(
                        t("edit_proposed_caption"),
                        value=interpretation.get("caption") or "",
                        key=f"manual_image_caption_{record.key}",
                    )
                    note = st.text_area(t("notes"), key=f"manual_image_note_{record.key}")
                    if st.button(t("save_image_observation_review"), key=f"save_manual_image_review_{record.key}"):
                        record.human_validations["image_interpretation"] = {
                            "decision": decision,
                            "edited_caption": edited_caption,
                            "note": note,
                        }
                        st.success(t("saved_image_observation_review"))

        # SELECT
        render_record_selector()

    # EVIDENCE QUERIES (Hidden by default)
    if SHOW_DIRECT_EVIDENCE_TABLES and st.session_state.evidence_answers:
        st.header(t("direct_evidence"))
        for ans in st.session_state.evidence_answers.values():
            st.subheader(ans.label)
            if ans.items:
                st.dataframe(pd.DataFrame(_sanitize_rows(ans.items)))
            for n in ans.notes:
                st.caption(n)

    # PROFILE
    if st.session_state.selected_records:
        render_selected_records(st.session_state.selected_records)
        
        if st.button(t("build_profile")):
            with st.spinner("Building schema and extracting claims..."):
                st.session_state.profile = build_profile(query, st.session_state.selected_records)

    # CLAIM REVIEW
    if st.session_state.profile:
        st.header(t("claim_review"))
        st.caption(t("claim_review_caption"))

        records_by_key = {r.key: r for r in st.session_state.selected_records}
        df = _claims_to_df(st.session_state.profile.extracted_claims, records_by_key=records_by_key)
        hidden_columns = ["_confidence_explanation", "claim_id", "record_key", "source_field", "claim_type", "internal confidence", "raw evidence_span"]
        column_config = _claim_column_config()
        st.caption(t("claim_review_action_hint"))
        if DEBUG_UI:
            hidden_columns = []

        edited = st.data_editor(
            df,
            width="stretch",
            hide_index=True,
            column_config=column_config,
            column_order=[c for c in df.columns if c not in hidden_columns],
            disabled=["Field", "Extracted claim", "Source", "Original record", "Where found"],
        )
        for hidden in hidden_columns:
            if hidden not in edited.columns and hidden in df.columns:
                edited[hidden] = df[hidden]

        if st.button(t("apply_review")):
            with st.spinner("Processing claims and computing uncertainty signals..."):
                validated = _df_to_claims(edited)
                st.session_state.validated_claims = validated
                for record in st.session_state.selected_records:
                    record.human_validations.setdefault("claim_review", {})
                for _, row in edited.iterrows():
                    key = row.get("record_key")
                    if key in records_by_key:
                        records_by_key[key].human_validations["claim_review"][row.get("claim_id", "")] = {
                            "decision": row.get("Human decision"),
                            "edited_value": row.get("Edit value"),
                            "notes": row.get("Notes"),
                        }

                table = build_claim_family_table(validated)

                st.session_state.validated_table = table
                st.session_state.validated_signals = None
                identity_status = _identity_status()
                st.session_state.recommendations = recommend_from_claims(validated, identity_status=identity_status)
                st.session_state.recommendation_identity_status = identity_status

    # COMPARISON
    if st.session_state.validated_table:
        st.header(t("compare_selected"))

        rows = []
        for f, row in st.session_state.validated_table.items():
            r = {"field": f}
            r.update(row)
            rows.append(r)

        st.dataframe(pd.DataFrame(_sanitize_rows(rows)))

    if st.session_state.validated_table:
        render_identity_status_control()
        identity_status = _identity_status()
        if (
            st.session_state.validated_claims
            and st.session_state.recommendation_identity_status != identity_status
        ):
            st.session_state.recommendations = recommend_from_claims(
                st.session_state.validated_claims,
                identity_status=identity_status,
            )
            st.session_state.recommendation_identity_status = identity_status

    # RECOMMENDATIONS
    if st.session_state.recommendations is not None:
        render_recommendations(st.session_state.recommendations)

    st.header(t("semantic_workspace"))
    render_merge_controls(st.session_state.semantic_graph)
    render_semantic_graph(st.session_state.semantic_graph, show_header=False)
    render_export_tools(
        st.session_state.semantic_graph,
        query=query,
        selected_records=st.session_state.selected_records,
        validated_claims=st.session_state.validated_claims,
        signals=st.session_state.validated_signals,
    )
    render_sparql_tools(st.session_state.semantic_graph)


if __name__ == "__main__":
    main()
