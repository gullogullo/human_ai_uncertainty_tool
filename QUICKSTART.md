# Quick Start Guide

## Installation

```bash
cd /Users/andreagulli/human_ai_uncertainty_tool
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

## Run The Tool

```bash
python main.py
```

Or directly with Streamlit:

```bash
streamlit run src/ui.py
```

The browser should open automatically. If not, visit `http://localhost:8501`.

## Try An Example

1. Enter a query such as `Ruckers harpsichord`.
2. Click **Search**.
3. Inspect the retrieved record ecosystem graph.
4. Open retrieved records and review their source metadata, image, URL, and evidence snippets.
5. Optionally add external or manual evidence.
6. Select records to consider.
7. Within any selected record that has an image, optionally run visual indexing and review the proposed visual observations.
8. Click **Use selected records**.
9. Review extracted claims.
10. Apply the review.
11. Set the identity status for the selected research set.
12. Review semantic modeling proposals.
13. Accept proposals into the semantic graph, or remove accepted proposals if needed.
14. Inspect and optionally merge nodes in the semantic workspace graph.
15. Export the semantic graph as JSON/Turtle or query it with SPARQL.

## Identity Status

Selected records are not assumed to describe the same object.

The identity-status selector controls how semantic proposals are scoped:

- `no_identity_claim`: default; selected records are treated as separate witnesses.
- `candidate_match`: records may describe the same object, but this is not asserted.
- `user_asserted_same_object`: the user asserts that selected records describe the same object.
- `source_asserted_same_object`: a source or authority asserts same-object identity.

By default, accepted semantic proposals are record-local. Same-object assertions are only appropriate when identity status permits them.

## What To Look For

### Retrieved Record Ecosystem

The first graph is a retrieval/evidence graph. It shows the query, retrieved records, source pages, images, and retrieval cues. It does not assert semantic identity or object equivalence.

### Claim Review

The claim review table contains extracted claim-like values such as maker, date, material, and object type. The user decides whether each claim should be accepted, rejected, edited, or left unsure.

### Semantic Modeling Proposals

Each proposal translates an accepted or reviewed claim into a possible semantic graph addition.

Proposal cards show:

- a human-readable action
- a plain-language claim
- scope
- evidence/provenance
- a risk note
- a mini graph preview
- a collapsed technical CRM mapping

`Accept -> Graph` adds the proposal to the in-session semantic graph. Accepted proposals can be removed with **Remove from graph**.

### Semantic Workspace Graph

This is the graph of accepted semantic assertions. It is separate from the retrieval graph.

Node merging happens only here. Merging semantic nodes rewires the semantic graph and should be used deliberately.

## Module Overview

| Module | Purpose |
|--------|---------|
| `retrieval.py` | Query API-backed sources |
| `non_api_retrieval.py` | Non-API source helpers and fallback dataset ingestion |
| `graph_builder.py` | Build the retrieval/evidence graph |
| `claim_extraction.py` | Extract reviewable claims from selected records |
| `semantic_templates.py` | CIDOC CRM / MIMO template patterns |
| `semantic_recommendations.py` | Build plain-language semantic modeling proposals |
| `semantic_graph.py` | Add, remove, merge, and serialize semantic graph content |
| `export_semantic.py` | Export semantic graph as JSON/Turtle |
| `sparql.py` | Query local semantic graph or remote SPARQL endpoints |
| `visualization.py` | Render PyVis graphs |
| `ui.py` | Streamlit interface |
| `models.py` | Data classes and enums |
| `settings.py` | Configuration and source registry |

## Export

The app supports:

- semantic graph JSON
- semantic graph Turtle
- analysis context JSON

The analysis context includes the query, selected records, reviewed claims, and identity status.

## Troubleshooting

### Slow query responses

- Europeana queries can be slow without an API key.
- The Met API is rate-limited.
- Non-API sources can be unavailable or blocked.
- Use curated JSON/JSONL fallback datasets when needed.
- Try shorter, more specific queries.

### No results for a query

Not all sources return results for all queries:

- Europeana is broad and aggregator-oriented.
- The Met is strongest for its own collection.
- Boalch and Philharmonie depend on permitted access or fallback datasets.

### Image interpretation unavailable

Image interpretation is optional. Without `OPENAI_API_KEY`, the app continues without vision-based interpretation.

### Visual indexing unavailable

Visual indexing uses local zero-shot OpenCLIP inference. It does not require training, but the pretrained model weights must be available to `open-clip-torch`; first use may download them if they are not already cached.

## Important Notes

- The old visible uncertainty-signals workflow has been removed.
- Selection means “consider these records,” not “merge these records.”
- The retrieval graph and semantic graph are separate.
- Accepted semantic proposals are reversible.
- Manual semantic node merges are not automatically reversible.
