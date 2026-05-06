# REM@KE Record Ecosystem & Uncertainty Explorer - Changelog

**Version 1.0 - Record-Centered Refactoring**  
**Date:** 1 maggio 2026

## Overview

This major release transforms REM@KE from a record-merging tool to a **record-centered uncertainty exploration interface**. Records are now treated as separate witnesses, with the goal of inspecting how sources describe, omit, or contradict information for a query.

**New Title:** REM@KE — Record Ecosystems & Uncertainty Explorer

## Breaking Changes

### Removed: Wikidata Integration
- **Impact:** Wikidata is no longer retrieved or displayed
- **Why:** Focus shifted to concrete cultural heritage records, not semantic expansion
- **Migration:** If you relied on Wikidata, switch to Boalch, Philharmonie, Europeana, or The Met

### Changed: Search Results
- `search_all_sources()` now returns only: Europeana, The Met, Boalch, Philharmonie
- No longer includes Wikidata, Rijksmuseum, or V&A by default
- Records from Boalch and Philharmonie are optional (fall back to manual datasets)

## New Features

### 1. Non-API Sources: Boalch & Philharmonie
**Files:** `src/non_api_retrieval.py`

#### Boalch–Mould Online (boalch.org)
- Scrapes keyboard instrument records with ethical constraints
- Respects robots.txt
- Falls back to manually curated datasets
- Uses polite user-agent and reasonable timeouts

**Record Type:** `non_api_curated`, `source_type: "authority_database"`

#### Philharmonie de Paris Museum Collections
- Scrapes museum collection records (emphasis on musical instruments)
- Supports image extraction
- Falls back to manual datasets
- Ethical scraping with rate limiting

**Record Type:** `non_api_curated`, `source_type: "museum_collection"`

#### Manual Dataset Support
```python
load_manual_dataset("boalch", "boalch")  # Loads data/boalch_boalch.json or .jsonl
load_manual_dataset("philharmonie", "philharmonie")  # Loads data/philharmonie_philharmonie.json or .jsonl
```

**Dataset Format:**
```json
{
  "records": [
    {
      "object_id": "...",
      "title": "...",
      "maker": "...",
      "date": "...",
      "object_name": "...",
      "image_url": "...",
      "source_url": "...",
      "location": "...",
      "description": "..."
    }
  ]
}
```

### 2. AI Image Interpretation Layer
**File:** `src/image_interpretation.py`

```python
def interpret_record_image(record: Record) -> dict:
    """
    Returns: {
        "visible_object_type": "harpsichord",
        "visible_materials": ["wood", "ivory"],
        "visible_features": ["keyboard", "case", "lid"],
        "uncertain_observations": ["..."],
        "caption": "...",
        "model": "openai_gpt4_vision",
        "confidence_note": "AI interpretation; requires human validation",
        "success": bool
    }
    """
```

**Requires:** `OPENAI_API_KEY` environment variable (optional)  
**Fallback:** Returns empty structure with error message if not configured

**Multimodal Consistency:**
```python
compare_image_text_consistency(image_interpretation, textual_claims)
```
Compares AI-derived observations against textual metadata, warns about confidence requirements.

### 3. Extended Record Model
**File:** `src/models.py`

New fields in `Record` dataclass:
```python
source_type: Optional[str] = None  # "api_museum", "authority_database", "user_added_evidence", etc.
evidence_spans: list = field(default_factory=list)  # Raw text snippets, page references
local_image_path: Optional[str] = None  # Path to uploaded image
human_validations: dict = field(default_factory=dict)  # User Accept/Reject/Unsure decisions
```

### 4. Source Registry
**File:** `src/settings.py`

```python
SOURCE_REGISTRY = {
    "europeana": {"type": "api_aggregator", "label": "Europeana", "enabled": True},
    "the_met": {"type": "api_museum", "label": "The Met", "enabled": True},
    "boalch": {"type": "authority_database", "label": "Boalch–Mould Online", "enabled": True},
    "philharmonie": {"type": "museum_collection", "label": "Philharmonie de Paris", "enabled": True},
    "manual": {"type": "user_added_evidence", "label": "Manual / External Record", "enabled": True}
}
```

### 5. Manual Record Ingestion
**UI Section:** "Add external or manual record"

Users can add:
- Title, source label, maker, date, object type
- Location, materials, description, source URL
- Optional image upload
- Creates Record with `retrieval_class="manual_user_added"`

Uploaded images are temporarily stored and can be used for visual claim extraction.

### 6. Improved Graph Visualization
**File:** `src/visualization.py`

**Physics Changes:**
- Reduced iterations: 250 → 150
- Lowered gravitational constant: -7000 → -4000
- Increased central gravity: 0.2 → 0.3
- Increased spring length: 150 → 200
- Reduced spring constant: 0.02 → 0.008
- Added damping: 0.4
- Added adaptive timestep

**Result:** Graph stabilizes faster and doesn't stick/drag during interaction

**Tooltip Improvements:**
- Query nodes: "Search query: {query}"
- Record nodes: Title, source, URL, retrieval explanation, metadata preview
- Media nodes: Image preview using HTML `<img>` tag with max dimensions
- Claim nodes: Field, value, source record, clickable link
- Technical keys hidden unless `DEBUG_UI=True`

**Edge Labels:**
- "≈ exact match" instead of "exact_title_match"
- "~ title match" instead of "title_match"
- "→ in description" instead of "description_match"
- Etc.

### 7. Redesigned UI Sections
**File:** `src/ui.py`

| Old Name | New Name | Purpose |
|----------|----------|---------|
| "Evidence Graph" | "Retrieved Record Ecosystem" | Emphasize records as witnesses, not merged object |
| "Select records from graph..." | "Select records" | Frame as comparison, not extraction |
| "Analyze selected subgraph" | "Compare selected records" | Parallel phrasing |
| "Claim validation" | "Claim Review" | More approachable, less technical |
| "Uncertainty" | "Uncertainty Explanations" | Emphasize explanations, not raw metrics |

**New Sections:**
- "Add external or manual record" - Manual record ingestion form
- Record display with full metadata, images, links

### 8. Human-Readable Claim Review
**Previous:** Technical columns (claim_id, record_key, source_field, confidence, evidence_span)  
**Now:**

Visible Columns:
- `keep` - Include/exclude claim
- `field` - Field name
- `claim` - Extracted value
- `source` - Source name
- `where_found` - Field or extraction method
- `decision` - Accept / Reject / Unsure
- `notes` - User annotations

Hidden Columns (DEBUG mode):
- `claim_id`
- `record_key`
- `claim_type`
- `confidence`
- `evidence_span`

### 9. Natural Language Uncertainty Explanations
**Function:** `render_uncertainty_explanations()` in `src/ui.py`

For each field, displays:

**Missingness:**
```
Coverage: X% of records provide this field
How computed: records_with_value / total_selected_records
```

**Textual Disagreement:**
```
Variation: Different values appear across records
How computed: Text similarity comparison (heuristic, not authoritative)
⚠️ Warning: May have false positives
```

**Multimodal Consistency:**
```
Consistency: high / medium / low / uncertain
How computed: AI image interpretation vs textual claims comparison
⚠️ Important: AI interpretation requires human validation
```

Expandable sections explain computation methods.

### 10. Enhanced Export
**New Function:** `export_analysis_context()` in `src/ui.py`

Exports JSON with:
```json
{
  "timestamp": "ISO-8601",
  "query": "user query",
  "selected_records": [
    {
      "object_id": "...",
      "source": "...",
      "source_type": "...",
      "retrieval_class": "...",
      "title": "...",
      "source_url": "...",
      "metadata": {...}
    }
  ],
  "validated_claims": [...],
  "uncertainty_signals": [...]
}
```

## Configuration Changes

### New Settings (`src/settings.py`)

```python
# Ethical scraping
BOALCH_BASE_URL = "https://www.boalch.org"
PHILHARMONIE_BASE_URL = "https://collectionsdumusee.philharmoniedeparis.fr"

# UI behavior
DEBUG_UI = False  # Show technical columns (claim_id, record_key, etc.) when True
SHOW_DIRECT_EVIDENCE_TABLES = False  # Hidden by default

# Source registry
SOURCE_REGISTRY = {...}  # See above
```

### Removed Settings
- `WIKIDATA_API` - No longer used
- `RIJKSMUSEUM_SEARCH_API` - No longer in search_all_sources()
- `VICTORIA_AND_ALBERT_API` - No longer in search_all_sources()

## API Changes

### Retrieval Module

```python
# Before
search_all_sources(query)
# Returns: {"europeana": [...], "the_met": [...], "wikidata": [...], ...}

# After
search_all_sources(query)
# Returns: {"europeana": [...], "the_met": [...], "boalch": [...], "philharmonie": [...]}
```

New functions:
```python
search_boalch(query: str, rows: int = 10) -> List[Record]
search_philharmonie(query: str, rows: int = 10) -> List[Record]
load_manual_dataset(source: str, dataset_name: str) -> List[Record]
```

### Record Model

```python
# New fields
record.source_type: Optional[str]  # "api_museum", "authority_database", etc.
record.evidence_spans: list  # Raw text snippets
record.local_image_path: Optional[str]  # Uploaded image path
record.human_validations: dict  # User decisions
```

### Image Interpretation

```python
# New module
from src.image_interpretation import interpret_record_image, compare_image_text_consistency

result = interpret_record_image(record)
consistency = compare_image_text_consistency(result, textual_claims)
```

## Migration Guide

### For Existing Code

1. **Remove Wikidata references:**
   ```python
   # Old
   results = search_all_sources("harpsichord")
   wikidata_records = results["wikidata"]
   
   # New - just ignore wikidata key, it won't exist
   results = search_all_sources("harpsichord")
   # results = {"europeana": [...], "the_met": [...], "boalch": [...], "philharmonie": [...]}
   ```

2. **Update search_all_sources() calls:**
   ```python
   # Old
   for source in ["europeana", "the_met", "wikidata", "rijksmuseum"]:
       records = results[source]
   
   # New
   for source in ["europeana", "the_met", "boalch", "philharmonie"]:
       records = results[source]
       if records:  # May be empty if scraping fails
           process_records(records)
   ```

3. **Add robustness for non-API sources:**
   ```python
   # Non-API sources may return [] if scraping fails or is blocked
   boalch_records = results["boalch"]
   if not boalch_records:
       logger.warning("Boalch scraping failed, no manual dataset available")
   ```

### For UI Users

1. **Manual records are now first-class:** You can add external records before or after automated search
2. **Claim Review is more user-friendly:** Use Accept/Reject/Unsure instead of mysterious confidence scores
3. **Uncertainty is explained:** Each signal includes "How was this computed" expandable section
4. **Direct evidence tables hidden:** They're still available (set `SHOW_DIRECT_EVIDENCE_TABLES=True`) but not shown by default

## Performance Notes

- Reduced graph physics iterations improve rendering speed on large networks
- Image interpretation is optional (graceful fallback if OpenAI API not configured)
- Manual dataset loading is instant (local JSON/JSONL)
- Non-API scraping respects robots.txt and uses polite timeouts

## Troubleshooting

### "Boalch/Philharmonie search returned empty results"
1. Check robots.txt block status (logs show warning)
2. Look for manual dataset: `data/boalch.json` or `data/philharmonie.json`
3. Try manual record ingestion as fallback

### "Image interpretation not available"
- Ensure `OPENAI_API_KEY` environment variable is set
- App will still work, just won't compare images vs text

### "Graph is sticky/unresponsive"
- Physics tuning reduced but may need further adjustment
- Try reducing number of records selected
- Set `DEBUG_UI=True` to see underlying node data

## Testing Checklist

- [ ] Search returns results from Europeana and The Met
- [ ] Boalch search fails gracefully (returns empty or uses manual dataset)
- [ ] Philharmonie search fails gracefully
- [ ] Manual record ingestion works with image upload
- [ ] Graph renders without sticking
- [ ] Hovering over nodes shows readable tooltips
- [ ] Hovering over media nodes shows image preview
- [ ] Claim review shows user-friendly columns
- [ ] Uncertainty explanations are readable (not just numbers)
- [ ] DEBUG_UI toggle works
- [ ] Export JSON includes all required fields
- [ ] No Wikidata nodes appear in graph

## Known Issues & Limitations

1. **Non-API Scraping:** HTML selectors may need updating if sites change layout
2. **Image Interpretation:** Requires OpenAI account and API key; not free
3. **Manual Datasets:** Must be manually curated and placed in `data/` directory
4. **Physics Tuning:** May need further adjustment for very large networks
5. **Graph Export:** Semantic graph export unchanged, only analysis export is new

## Future Roadmap

- [ ] Add user authentication for persistent manual records
- [ ] Implement caching for image interpretations
- [ ] Expand non-API source coverage
- [ ] Add record versioning and change tracking
- [ ] Bulk import for manual records (CSV/XLSX)
- [ ] API endpoint for programmatic access
- [ ] Improved handling of heterogeneous metadata schemas
- [ ] Uncertainty metric validation against ground truth
