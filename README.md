# REM@KE — Source Records & Semantic Modeling Workspace

A human-in-the-loop Streamlit tool for searching cultural heritage records, reviewing extracted claims, and building a provenance-aware semantic graph without assuming that selected records describe the same object.

## Goal

REM@KE helps researchers inspect heterogeneous cultural heritage records as separate witnesses. A selected set may contain related records, analogues, candidate matches, or records that a user/source explicitly treats as the same object. The tool keeps that identity status explicit and avoids hidden merging.

## Current Workflow

1. **Search source records**
   - Query supported cultural heritage sources.
   - Retrieved records are shown as source witnesses, not as semantic assertions.

2. **Inspect the retrieved record ecosystem**
   - The first graph shows retrieval context, source records, record pages, images, and unvalidated retrieval cues.
   - It does not assert identity, equivalence, or semantic relations between records.

3. **Add external or manual evidence**
   - Add manually entered evidence.
   - Paste copied text from non-API sources when useful.
   - Optionally attach or upload an image.

4. **Select records to consider**
   - Selection means “include these records in the research set.”
   - Selection does not mean “merge these records” or “these records describe the same object.”

5. **Review extracted claims**
   - The app extracts claim-like values such as maker, date, material, and present object type.
   - The user accepts, rejects, edits, or marks claims as unsure.
   - Only reviewed claims feed semantic modeling proposals.

6. **Set identity status**
   - `no_identity_claim`: default; selected records are separate witnesses.
   - `candidate_match`: records may describe the same object, but this is not asserted.
   - `user_asserted_same_object`: the user asserts same-object identity.
   - `source_asserted_same_object`: a source/authority asserts same-object identity.

7. **Review semantic modeling proposals**
   - Each proposal is shown first in plain language.
   - CIDOC CRM/MIMO details are available in a collapsed technical mapping.
   - Proposals are record-local by default and preserve provenance.
   - Accepted proposals can be removed from the graph.

8. **Edit the semantic workspace graph**
   - Accepted proposals add nodes and edges to the in-session semantic graph.
   - Merge controls are shown before the graph so changes are immediately visible.
   - Node merging modifies only the semantic workspace graph, not the retrieval graph.

9. **Export or query**
   - Export the semantic graph as JSON or Turtle.
   - Export analysis context as JSON.
   - Query the in-session semantic graph with SPARQL.

## Key Design Principles

- **Records are witnesses, not automatically identical objects.**
- **Selection is not merging.**
- **The retrieval graph is not the semantic graph.**
- **Semantic assertions require human acceptance.**
- **Accepted assertions are provenance-aware and reversible.**
- **CIDOC CRM is used as technical backing, not as the primary user-facing explanation.**
- **Object-level assertions are only appropriate when identity status permits them.**

## Features

- Multi-source retrieval from Europeana, The Met, Victoria and Albert Museum, Boalch-Mould Online, and Philharmonie de Paris Museum Collections.
- Manual and external evidence entry.
- Claim review with Accept / Reject / Unsure decisions and editable values.
- Explicit identity-status layer for selected records.
- Plain-language semantic modeling proposals.
- Collapsed technical CRM/MIMO mapping for specialists.
- Mini-graph previews for proposed semantic assertions.
- Reversible `Accept -> Graph` behavior.
- In-session semantic graph visualization and node merging.
- JSON, Turtle, and SPARQL support for the semantic graph.
- English and Italian UI text for the main workflow and semantic proposal cards.

## Project Structure

```text
human_ai_uncertainty_tool/
├── main.py
├── requirements.txt
├── src/
│   ├── models.py                  # Core data classes and enums
│   ├── retrieval.py               # API retrieval
│   ├── non_api_retrieval.py       # Non-API source helpers and fallback datasets
│   ├── graph_builder.py           # Retrieval/evidence graph construction
│   ├── claim_extraction.py        # Claim extraction from selected records
│   ├── semantic_templates.py      # CIDOC CRM / MIMO template patterns
│   ├── semantic_recommendations.py# Plain-language semantic proposals
│   ├── semantic_graph.py          # In-session semantic graph operations
│   ├── export_semantic.py         # JSON/Turtle export helpers
│   ├── sparql.py                  # Local and remote SPARQL helpers
│   ├── visualization.py           # PyVis graph rendering
│   ├── image_interpretation.py    # Optional image interpretation
│   └── ui.py                      # Streamlit interface
└── data/
```

## Installation

```bash
cd human_ai_uncertainty_tool
pip install -r requirements.txt
```

Optional Europeana API key:

```bash
export EUROPEANA_KEY="<your-key>"
```

Optional OpenAI API key for image interpretation:

```bash
export OPENAI_API_KEY="<your-key>"
```

## Usage

```bash
python main.py
```

Or directly:

```bash
streamlit run src/ui.py
```

## Important Notes

- The old visible **Uncertainty Explanations** section has been removed from the current UI.
- Signal-related modules may still exist in the codebase for compatibility or future reuse, but they are no longer the main user-facing workflow.
- `Accept -> Graph` is reversible for proposal additions created with the current provenance format.
- Manual node merges are semantic graph edits. They are not automatically reversible and should be used deliberately.

## Limitations

- The semantic graph is currently in-session; persistence depends on export.
- Non-API sources may be unavailable or blocked; fallback datasets are supported.
- CIDOC CRM mappings are lightweight proposal templates, not a complete ontology engineering environment.
- Identity status is user/source declared; the tool does not prove identity.

## License

MIT
