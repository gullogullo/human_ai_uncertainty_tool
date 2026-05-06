# Implementation Notes - Source Witness And Semantic Workspace Refactoring

## Current Architecture

REM@KE is organized around two separate graph layers:

1. **Retrieved record ecosystem graph**
   - Built from search results and manual/external evidence.
   - Shows query context, retrieved records, source pages, images, and retrieval cues.
   - Does not assert identity, equivalence, or semantic relations between records.

2. **Semantic workspace graph**
   - Built only from accepted semantic modeling proposals and later semantic edits.
   - Can be exported as JSON/Turtle and queried with SPARQL.
   - Supports reversible proposal additions and manual node merging.

This separation is central. Selection in the retrieval layer does not imply merging in the semantic layer.

## Record-Witness Model

Records are first-class witnesses. A selected record set may contain:

- related witnesses
- analogues
- candidate matches
- separate objects
- records that the user/source explicitly treats as the same object

The app does not infer same-object identity from retrieval, selection, or textual similarity.

Each `Record` carries:

- `retrieval_class`: how the record was found
- `source_type`: source category
- `is_semantic_anchor`: kept false in the current design
- `human_validations`: claim review decisions
- source metadata, raw payload, URL, image URL, and optional local image path
- optional `visual_indexing` and `image_text_alignment` raw payloads for reviewed zero-shot image evidence

## Identity Status Layer

`IdentityStatus` is defined in `src/models.py` with four values:

- `no_identity_claim`
- `candidate_match`
- `user_asserted_same_object`
- `source_asserted_same_object`

Default is `no_identity_claim`.

Identity status is stored in Streamlit session state as `identity_status`. It is selected after claim review and before semantic proposal review.

Semantic recommendation generation receives the identity status:

```python
recommend_from_claims(validated_claims, identity_status=identity_status)
```

For `no_identity_claim` and `candidate_match`, semantic object/event nodes are localized to the source record, for example:

```text
Instrument (the_met:501789)
Production (the_met:501789)
```

For `user_asserted_same_object` and `source_asserted_same_object`, shared object-level nodes are allowed.

## Claim Review

Claim extraction produces reviewable `ExtractedClaim` objects from selected records. The UI presents user-facing columns while preserving internal identifiers in hidden columns.

Human decisions are mapped as:

- Accept -> confidence `0.8`
- Unsure -> confidence `0.5`
- Reject -> confidence `0.2`

Reviewed claims feed the semantic proposal builder.

Accepted visual-indexing observations are converted into reviewable claims with `source_field` set to `visual_indexing` or `image_text_alignment`. Their evidence spans preserve the model/method, score, and alignment summary so the claim list keeps visible provenance.

## Semantic Modeling Proposals

Semantic proposals are generated in `src/semantic_recommendations.py` from templates in `src/semantic_templates.py`.

Each `SemanticRecommendation` now includes user-facing proposal fields:

- `action_label`
- `plain_language_claim`
- `scope`
- `provenance_record_key`
- `source_field`
- `risk_note`
- `crm_pattern`
- `preview_nodes`
- `preview_edges`

The UI renders proposals with:

- badges for retrieved evidence, extracted claim, proposed/accepted assertion, and scope
- human-readable action and claim
- provenance and source-field information
- risk note
- mini graph preview
- collapsed technical CRM mapping

CIDOC CRM remains a technical mapping layer, not the primary explanation.

## Reversible Proposal Acceptance

`src/semantic_graph.py` supports:

- `add_recommendation(graph, rec)`
- `remove_recommendation(graph, recommendation_id)`
- `merge_nodes(graph, source_node_id, target_node_id)`

When a recommendation is accepted, provenance stores:

- recommendation id
- claim id
- source record
- scope
- provenance record key
- source field
- plain-language claim
- risk note
- `node_ids_added`
- `edge_keys_added`

Removal uses this provenance to remove only graph content introduced by that recommendation. Shared nodes or edges used by remaining accepted recommendations are preserved.

Manual node merging is not automatically reversible. It rewires graph edges, removes the source node, deduplicates edges, and appends merge provenance.

## Streamlit State

Important session keys:

- `graph`: retrieved record ecosystem graph
- `selected_records`: current research set
- `validated_claims`: reviewed claims
- `validated_table`: claim-family comparison table
- `recommendations`: current semantic modeling proposals
- `recommendation_identity_status`: identity status used to generate current recommendations
- `semantic_graph`: in-session semantic workspace graph
- `identity_status`: current identity-status selector value
- `ui_language`: English or Italiano

When identity status changes after claim review, recommendations are regenerated so scope and node localization stay consistent.

## UI Sections

Current main sections:

1. title, language, query/search
2. retrieved source records and retrieval graph
3. external/manual evidence entry
4. selected records
5. claim review
6. selected-record comparison table
7. identity status
8. semantic modeling proposals
9. semantic workspace graph with merge controls
10. export tools
11. SPARQL tools

The old visible **Uncertainty Explanations / Evidence & Interpretation Signals** section has been removed from the UI.

## Translation

The main UI supports English and Italian through `UI_TEXT` in `src/ui.py`.

Semantic proposal cards translate their primary user-facing parts at render time:

- action label
- plain-language claim
- scope label
- risk note
- buttons and section labels

The underlying recommendation data remains language-neutral enough for export and graph provenance.

## Deprecated Or Background Modules

Some modules remain for compatibility or possible future reuse:

- `signals.py`
- `prompts.py`
- `uncertainty_profile.py`
- parts of `embeddings.py`
- some image-text comparison helpers

These are no longer part of the main visible workflow. Avoid reintroducing uncertainty-signal UI unless the design is reconsidered.

## Export

Semantic graph export lives in `src/export_semantic.py`.

Supported outputs:

- semantic graph JSON
- semantic graph Turtle

`export_analysis_context()` in `src/ui.py` exports:

- timestamp
- query
- identity status
- selected records
- manual records
- validated claims

The older uncertainty-signal payload field may still exist structurally, but current UI flow sets `validated_signals` to `None`.

## Debug Mode

When `DEBUG_UI = True`:

- record expanders show object ids and raw keys
- claim review can expose hidden/internal columns
- graph tooltips include debug information

The previous debug view for uncertainty signal JSON is obsolete because the visible signal section has been removed.

## Performance Notes

Retrieval performance depends on source availability:

- Europeana: API-dependent and faster with a key
- The Met: API-backed but rate-limited
- Boalch/Philharmonie: may use scraping or fallback datasets

Graph rendering is PyVis-based. Large record sets or semantic graphs may render more slowly.

Semantic proposal generation is lightweight and rule/template-based.

## Testing Suggestions

Useful unit tests:

```python
test_recommendations_are_record_local_without_identity_claim()
test_recommendations_allow_shared_object_when_identity_asserted()
test_add_recommendation_records_added_nodes_and_edges()
test_remove_recommendation_preserves_shared_nodes()
test_merge_nodes_rewires_edges_and_records_provenance()
test_identity_status_change_regenerates_recommendations()
```

Useful integration tests:

```python
test_search_select_claim_review_accept_remove_export()
test_manual_record_claim_review_semantic_proposal()
test_language_switch_translates_semantic_proposal_cards()
test_semantic_graph_export_after_reversible_acceptance()
```

Manual QA checklist:

- Search produces retrieved record graph.
- Selecting records does not create semantic graph content.
- Claim review generates semantic proposals.
- Changing identity status regenerates proposal scope.
- Accepting a proposal adds graph content.
- Removing a proposal removes only its own graph content.
- Merge controls appear before semantic graph visualization.
- English/Italian language switch updates proposal card text.
- JSON/Turtle export reflects accepted semantic graph state.

## Maintenance Notes

- Keep README, QUICKSTART, and IMPLEMENTATION_NOTES aligned with the current workflow.
- Do not describe selected records as same-object records unless identity is asserted.
- Do not make CIDOC CRM labels the primary proposal UI.
- Keep proposal additions provenance-aware and reversible.
- Treat manual node merging as a deliberate semantic graph edit.
- Avoid reviving the old uncertainty/comparison-centered UI without a new design decision.
