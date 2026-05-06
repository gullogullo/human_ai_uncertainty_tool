"""Non-API retrieval sources: Boalch–Mould Online and Philharmonie de Paris Museum Collections."""

from __future__ import annotations

import logging
import json
import csv
import html
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urljoin, urlparse
import requests
from bs4 import BeautifulSoup

from src.models import Record, SourceSchema
from src.settings import ALLOW_USER_PROVIDED_NON_API_URL_FETCH, SOURCE_REGISTRY

logger = logging.getLogger(__name__)

# Polite scraping session
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "REMAKE/0.6 (Cultural Heritage Research; +https://remake.example.com)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9"
})

BOALCH_SCHEMA = SourceSchema(
    source="boalch",
    schema_name="Boalch–Mould Online (curated)",
    fields=["title", "maker", "date", "location", "object_name", "description"],
    field_groups={
        "title": "identification",
        "maker": "agents",
        "date": "time",
        "location": "place",
        "object_name": "classification",
        "description": "description",
    },
)

PHILHARMONIE_SCHEMA = SourceSchema(
    source="philharmonie",
    schema_name="Philharmonie de Paris Museum Collections (curated)",
    fields=["title", "maker", "date", "object_name", "image_url", "location", "description"],
    field_groups={
        "title": "identification",
        "maker": "agents",
        "date": "time",
        "object_name": "classification",
        "image_url": "media",
        "location": "place",
        "description": "description",
    },
)

CARMENTIS_SCHEMA = SourceSchema(
    source="carmentis",
    schema_name="Carmentis eMuseumPlus detail page",
    fields=["title", "maker", "date", "object_name", "materials", "dimensions", "inventory_number", "collection", "description"],
    field_groups={
        "title": "identification",
        "maker": "agents",
        "date": "time",
        "object_name": "classification",
        "materials": "material",
        "dimensions": "measurements",
        "inventory_number": "administrative",
        "collection": "administrative",
        "description": "description",
    },
)

NON_API_SOURCE_DOMAINS = {
    "boalch": {"boalch.org", "www.boalch.org"},
    "philharmonie": {"collectionsdumusee.philharmoniedeparis.fr"},
    "carmentis": {"carmentis.be", "www.carmentis.be"},
}

SECTION_LABELS = {
    "Base Information",
    "Maker/Marks/Origin",
    "Ownership History",
    "Keyboard and Specifications",
    "References",
    "Information Submitted By",
    "Old Boalch Numbers",
    "Vues",
    "Documentation",
}

KNOWN_DETAIL_LABELS = {
    "Date",
    "Date Notes",
    "Maker",
    "Notes about Attribution",
    "Marks",
    "Serial Number",
    "Serial Number Notes",
    "Present Owner",
    "Collection Details",
    "Catalog Number",
    "Instrument Location",
    "Provenance and Episodes",
    "Compass",
    "Compass Note",
    "Keyboard",
    "Disposition",
    "Stops",
    "Action",
    "Pitch",
    "Scale",
    "Description",
    "Dimensions",
    "Remarks",
    "References and Sources",
    "References",
    "Information Submitted By",
    "Old Boalch Numbers",
    "Title",
    "Maker / Author",
    "Inventory Number",
    "Collection",
    "Location",
    "Material",
    "Materials",
    "Object Type",
    "Instrument",
    "Type",
    "Where Made",
    "Owner",
    "Credit",
    "Caption",
    "Full Size",
    "Collection name",
    "Also known as",
    "Navigate",
    "Return to List",
    "Expand All Sections",
    "Serial#",
    "Serial No.",
    "Auteur",
    "Facteur",
    "Lieu",
    "Lieu de fabrication",
    "Numéro d'inventaire",
    "Numero d'inventaire",
    "Description",
    "Dimensions",
    "Étendue",
    "Etendue",
    "Matériaux",
    "Materiaux",
    "Marques et inscriptions",
    "Décor",
    "Decor",
    "Historique",
    "Localisation au Musée",
    "Localisation au Musee",
    "Livre(s)",
    "Article(s)",
    "Photo",
    "Object name",
    "Objectnaam",
    "Dénomination",
    "Denomination",
    "Title",
    "Titel",
    "Titre",
    "Artist/Maker",
    "Creator",
    "Auteur",
    "Vervaardiger",
    "Dating",
    "Datering",
    "Datation",
    "Technique",
    "Techniek",
    "Afmetingen",
    "Inventory number",
    "Inventarisnummer",
    "Numéro d'inventaire",
    "Object number",
    "Objectnummer",
    "Department",
    "Département",
    "Beschrijving",
}

BOALCH_NON_DATA_LABELS = {
    "Type",
    "Where Made",
    "Owner",
    "Credit",
    "Caption",
    "Full Size",
    "Collection name",
    "Also known as",
    "Navigate",
    "Return to List",
    "Expand All Sections",
    "Online Resources",
    "Edit Links (clear fields and update to delete link)",
    "Select",
    "Author/Date Spec",
    "( )",
}

BOALCH_BOILERPLATE_MARKERS = (
    "please upload more or better photos",
    "we are grateful to all copyright holders",
    "photo viewer",
    "return to list",
    "expand all sections",
    "online resources",
    "edit links",
    "edit instrument hyperlinks",
    "links cannot be saved",
    "citation reference",
    "bibliography record",
    "warning: edits to this entry",
    "cloned record",
    "admin code",
    "message text1",
    "i am the owner but wish to remain anonymous",
)


def _check_robots_txt(domain: str) -> bool:
    """
    Quick check if robots.txt allows scraping.
    Returns True if scraping is allowed or robots.txt is not found.
    This is a heuristic check, not authoritative.
    """
    try:
        res = SESSION.get(f"https://{domain}/robots.txt", timeout=5)
        if res.status_code == 404:
            return True
        content = res.text.lower()
        if "disallow: /" in content and "user-agent: *" in content:
            logger.warning(f"robots.txt on {domain} may disallow broad scraping")
            return False
        return True
    except Exception as e:
        logger.debug(f"Could not check robots.txt for {domain}: {e}")
        return True


def infer_non_api_source_from_url(url: str) -> Optional[str]:
    """Infer supported non-API source from a user-provided record URL."""
    domain = urlparse(url or "").netloc.lower()
    for source, domains in NON_API_SOURCE_DOMAINS.items():
        if domain in domains:
            return source
    return None


def fetch_record_from_source_url(url: str, source: Optional[str] = None) -> Optional[Record]:
    """
    Fetch and parse one user-provided non-API record page.

    This is deliberately not a crawler: it fetches only the URL supplied by the
    user, does not follow links, and returns None on failure or unsupported
    domains.
    """
    if not ALLOW_USER_PROVIDED_NON_API_URL_FETCH:
        logger.info("User-provided non-API URL fetching is disabled.")
        return None

    source = source or infer_non_api_source_from_url(url)
    if source not in NON_API_SOURCE_DOMAINS:
        logger.warning("Unsupported non-API source URL: %s", url)
        return None

    parsed = urlparse(url or "")
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in NON_API_SOURCE_DOMAINS[source]:
        logger.warning("URL does not match %s domains: %s", source, url)
        return None

    try:
        res = SESSION.get(url, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        if source == "boalch":
            return _parse_boalch_detail_page(url, soup, res.text)
        if source == "philharmonie":
            return _parse_philharmonie_detail_page(url, soup, res.text)
        if source == "carmentis":
            return _parse_carmentis_detail_page(url, soup, res.text)
    except Exception as exc:
        logger.warning("Single-page extraction failed for %s: %s", url, exc)
        return None
    return None


def parse_record_from_copied_text(text: str, source: str, source_url: Optional[str] = None) -> Optional[Record]:
    """
    Parse record text copied manually from the browser.

    This is the most reliable workaround for dynamic catalogues: the user copies
    the visible page content, and we parse that local text instead of depending
    on server-rendered HTML.
    """
    if source not in NON_API_SOURCE_DOMAINS or not (text or "").strip():
        return None

    try:
        if source == "boalch":
            record = _parse_boalch_copied_text(text, source_url)
            if record:
                return record
        lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
        pseudo_html = "<html><body>" + "".join(f"<div>{html.escape(line)}</div>" for line in lines) + "</body></html>"
        soup = BeautifulSoup(pseudo_html, "html.parser")
        url = source_url or f"manual-copied-text://{source}"
        if source == "boalch":
            record = _parse_boalch_detail_page(url, soup, text)
        if source == "philharmonie":
            record = _parse_philharmonie_detail_page(url, soup, text)
        if source == "carmentis":
            record = _parse_carmentis_detail_page(url, soup, text)
        if not source_url:
            record.source_url = None
        record.raw["copied_page_text"] = text[:20000]
        return record
    except Exception as exc:
        logger.warning("Copied text extraction failed for %s: %s", source, exc)
        return None
    return None


def _parse_boalch_copied_text(text: str, source_url: Optional[str] = None) -> Optional[Record]:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return None

    labels = {
        "Date Notes",
        "Maker",
        "Notes about Attribution",
        "Marks",
        "Serial Number Notes",
        "Present Owner",
        "Catalog Number",
        "Instrument Location",
        "Provenance and Episodes",
        "Compass",
        "Compass Note",
        "Keyboard",
        "Disposition",
        "Stops",
        "Action",
        "Pitch",
        "Scale",
        "Dimensions",
        "Description",
        "Remarks",
        "References and Sources",
        "Information Submitted By",
        "Old Boalch Numbers",
    }
    sections = {
        "Base Information",
        "Maker/Marks/Origin",
        "Ownership History",
        "Keyboard and Specifications",
        "References",
    }
    normalized_labels = {_normalize_label(label): label for label in labels}
    normalized_sections = {_normalize_label(label) for label in sections}
    pairs: Dict[str, Any] = {}
    raw_values: Dict[str, List[str]] = {}
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        normalized = _normalize_label(line)
        label = normalized_labels.get(normalized)
        if not label and normalized.startswith("present owner"):
            label = "Present Owner"
        if label:
            values = []
            idx += 1
            while idx < len(lines):
                next_norm = _normalize_label(lines[idx])
                if next_norm in normalized_labels or next_norm in normalized_sections or next_norm.startswith("present owner"):
                    break
                values.append(lines[idx])
                idx += 1
            if values:
                raw_values[label] = values
                pairs[label] = _clean_boalch_value_for_label(label, values)
            continue
        idx += 1

    maker_lines = raw_values.get("Maker") or _split_boalch_multiline(pairs.get("Maker"))
    maker = maker_lines[0] if maker_lines else None
    maker_details = " ".join(maker_lines[1:]) if len(maker_lines) > 1 else None
    owner_lines = raw_values.get("Present Owner") or _split_boalch_multiline(pairs.get("Present Owner"))
    collection = owner_lines[0] if owner_lines else None
    collection_location = owner_lines[1] if len(owner_lines) > 1 else None
    date = pairs.get("Date Notes")
    catalog_number = pairs.get("Catalog Number") or pairs.get("Serial Number Notes")
    location = pairs.get("Instrument Location") or collection_location
    object_name = _infer_object_name(text) or "instrument"
    description = _join_non_empty(pairs.get("Description"), pairs.get("Remarks"), pairs.get("Notes about Attribution"))
    source_specific = {
        **{k: v for k, v in pairs.items() if v},
        **({"Maker details": maker_details} if maker_details else {}),
        **({"Collection location": collection_location} if collection_location else {}),
    }

    if not any([maker, date, collection, location, catalog_number, description]):
        return None

    title_bits = [object_name, maker, date, f"catalog {catalog_number}" if catalog_number else None]
    title = " - ".join(bit for bit in title_bits if bit)
    metadata = {
        "title": title,
        "maker": maker,
        "date": date,
        "object_name": object_name,
        "location": location,
        "description": description,
        "inventory_number": catalog_number,
        "collection": collection,
        "source_specific": source_specific,
    }
    metadata = {k: v for k, v in metadata.items() if v}
    object_id = source_url.rstrip("/").split("/")[-1] if source_url else catalog_number or title
    return Record(
        object_id=object_id,
        source="boalch",
        title=title,
        metadata=metadata,
        image_url=None,
        source_url=source_url,
        raw={"copied_page_text": text[:20000], "parsed_pairs": source_specific},
        retrieval_class="non_api_curated",
        is_semantic_anchor=False,
        source_type=SOURCE_REGISTRY["boalch"]["type"],
        source_schema=BOALCH_SCHEMA,
        evidence_spans=_pairs_to_spans(source_specific),
    )


def _clean_boalch_value_for_label(label: str, values: List[str]) -> str:
    if label in {"Date Notes", "Marks", "Serial Number Notes", "Compass Note", "Keyboard", "Stops", "Action", "Pitch", "Scale", "Dimensions", "Description"}:
        values = [value for value in values if value not in {"Description"}]
    return " ".join(value for value in values if value).strip()


def _split_boalch_multiline(value: Any) -> List[str]:
    if not value:
        return []
    text = str(value)
    parts = re.split(r"\s{2,}|\s(?=\([A-Z][^)]+/[A-Z])", text)
    if len(parts) == 1:
        return [text]
    return [part.strip() for part in parts if part.strip()]


def parse_record_export_bytes(
    content: bytes,
    filename: str,
    source: str,
    source_url: Optional[str] = None,
) -> Optional[Record]:
    """Parse a user-downloaded single-record export file."""
    suffix = Path(filename or "").suffix.lower()
    try:
        if suffix == ".json":
            payload = json.loads(content.decode("utf-8-sig"))
            return _record_from_json_export(payload, source, source_url=source_url)
        if suffix == ".csv":
            text = content.decode("utf-8-sig")
            rows = list(csv.DictReader(text.splitlines()))
            if not rows:
                return None
            return _record_from_dataset_entry(source, rows[0], source_url=source_url, raw_key="csv_export")
        if suffix in {".html", ".htm"}:
            soup = BeautifulSoup(content.decode("utf-8-sig", errors="replace"), "html.parser")
            url = source_url or f"uploaded-html://{source}/{filename}"
            if source == "boalch":
                return _parse_boalch_detail_page(url, soup, content.decode("utf-8-sig", errors="replace"))
            if source == "philharmonie":
                return _parse_philharmonie_detail_page(url, soup, content.decode("utf-8-sig", errors="replace"))
            if source == "carmentis":
                return _parse_carmentis_detail_page(url, soup, content.decode("utf-8-sig", errors="replace"))
            return parse_record_from_copied_text(soup.get_text("\n", strip=True), source, source_url=url)
        if suffix == ".pdf":
            text = _extract_pdf_text(content)
            return parse_record_from_copied_text(text, source, source_url=source_url)
    except Exception as exc:
        logger.warning("Record export parsing failed for %s (%s): %s", filename, source, exc)
        return None
    return None


def _record_from_json_export(payload: Any, source: str, source_url: Optional[str] = None) -> Optional[Record]:
    if isinstance(payload, list):
        payload = payload[0] if payload else {}
    if not isinstance(payload, dict):
        return None

    if _looks_like_iiif_manifest(payload):
        return _record_from_iiif_manifest(payload, source=source, source_url=source_url)

    flattened = _flatten_json(payload)
    return _record_from_dataset_entry(source, flattened, source_url=source_url, raw_key="json_export", original_payload=payload)


def _record_from_dataset_entry(
    source: str,
    entry: Dict[str, Any],
    source_url: Optional[str] = None,
    raw_key: str = "dataset_entry",
    original_payload: Optional[Any] = None,
) -> Optional[Record]:
    title = _pick_export_value(entry, "title", "name", "_primaryTitle", "object.title", "record.title") or "Unknown"
    maker = _pick_export_value(entry, "maker", "Artist/Maker", "artist", "creator", "artistDisplayName", "author", "record.artistDisplayName")
    date = _pick_export_value(entry, "date", "year", "Date Notes", "objectDate", "dating", "record.objectDate")
    object_name = _pick_export_value(entry, "object_name", "objectName", "object_type", "type", "classification", "denomination", "record.objectName")
    description = _pick_export_value(entry, "description", "summary", "summaryDescription", "record.summaryDescription")
    location = _pick_export_value(entry, "location", "Instrument Location", "place", "department", "record.department")
    materials = _pick_export_value(entry, "materials", "material", "medium", "materialsAndTechniques", "record.medium")
    dimensions = _pick_export_value(entry, "dimensions", "dimension", "measurements")
    inventory_number = _pick_export_value(entry, "inventory_number", "inventoryNumber", "Catalog Number", "catalog_number", "object_id", "objectId", "id", "systemNumber", "record.systemNumber")
    image_url = _pick_export_value(entry, "image_url", "image", "primaryImageSmall", "primaryImage", "thumbnail", "record.primaryImageSmall")
    original_url = source_url or _pick_export_value(entry, "source_url", "url", "objectURL", "record.objectURL")

    metadata = {
        "title": title,
        "maker": maker,
        "date": date,
        "object_name": object_name,
        "location": location,
        "description": description,
        "materials": materials,
        "dimensions": dimensions,
        "inventory_number": inventory_number,
        "collection": _pick_export_value(entry, "collection", "Present Owner", "Collection Details"),
        "source_specific": entry,
    }
    metadata = {k: v for k, v in metadata.items() if v}
    if title == "Unknown":
        title_bits = [object_name, maker, date, inventory_number]
        title = " - ".join(bit for bit in title_bits if bit) or title
        metadata["title"] = title
    source_type = SOURCE_REGISTRY.get(source, SOURCE_REGISTRY["manual"])["type"]
    raw_payload = original_payload if original_payload is not None else entry
    return Record(
        object_id=str(inventory_number or title),
        source=source,
        title=title,
        metadata=metadata,
        image_url=image_url,
        source_url=original_url,
        raw={raw_key: raw_payload},
        retrieval_class="non_api_curated" if source not in {"manual", "victoria_and_albert"} else ("retrieval_match" if source == "victoria_and_albert" else "manual_user_added"),
        is_semantic_anchor=False,
        source_type=source_type,
        source_schema=_schema_for_export_source(source),
        evidence_spans=_pairs_to_spans({k: v for k, v in metadata.items() if k != "source_specific"}),
    )


def _record_from_iiif_manifest(payload: Dict[str, Any], source: str, source_url: Optional[str] = None) -> Optional[Record]:
    metadata_items = {}
    manifest_metadata = payload.get("metadata", [])
    if not isinstance(manifest_metadata, list):
        manifest_metadata = []
    for item in manifest_metadata:
        label = _iiif_text(item.get("label"))
        value = _iiif_text(item.get("value"))
        if label and value:
            metadata_items[label] = value
    label = _iiif_text(payload.get("label")) or "Unknown"
    entry = {
        **metadata_items,
        "title": label,
        "source_url": source_url or payload.get("homepage") or payload.get("@id") or payload.get("id"),
        "image_url": _iiif_manifest_image(payload),
    }
    return _record_from_dataset_entry(source, entry, source_url=source_url, raw_key="iiif_manifest", original_payload=payload)


def _looks_like_iiif_manifest(payload: Dict[str, Any]) -> bool:
    context = payload.get("@context") or payload.get("context")
    if isinstance(context, list):
        context = " ".join(str(item) for item in context)
    return "iiif" in str(context).lower() or str(payload.get("type", "")).lower() == "manifest"


def _iiif_text(value: Any) -> str:
    if isinstance(value, dict):
        values = []
        for item in value.values():
            if isinstance(item, list):
                values.extend(str(v) for v in item)
            else:
                values.append(str(item))
        return " | ".join(v for v in values if v)
    if isinstance(value, list):
        return " | ".join(_iiif_text(item) for item in value if _iiif_text(item))
    return str(value or "").strip()


def _iiif_manifest_image(payload: Dict[str, Any]) -> Optional[str]:
    try:
        canvases = payload.get("items") or payload.get("sequences", [{}])[0].get("canvases", [])
        first = canvases[0]
        annotations = first.get("items") or first.get("images", [])
        body = annotations[0].get("items", [annotations[0]])[0].get("body") if annotations else None
        if isinstance(body, list):
            body = body[0]
        if isinstance(body, dict):
            return body.get("id") or body.get("@id")
    except Exception:
        return None
    return None


def _extract_pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader
        import io

        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise RuntimeError("PDF parsing requires readable text and the pypdf package") from exc


def _flatten_json(value: Any, prefix: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(item, (dict, list)):
                out.update(_flatten_json(item, path))
            else:
                out[path] = item
                out[str(key)] = item
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            path = f"{prefix}.{idx}" if prefix else str(idx)
            if isinstance(item, (dict, list)):
                out.update(_flatten_json(item, path))
    return out


def _pick_export_value(entry: Dict[str, Any], *keys: str) -> Optional[str]:
    normalized = {_normalize_label(k): v for k, v in entry.items()}
    for key in keys:
        value = entry.get(key)
        if value in (None, "", [], {}):
            value = normalized.get(_normalize_label(key))
        text = _stringify_export_value(value)
        if text:
            return text
    return None


def _stringify_export_value(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, list):
        return " | ".join(_stringify_export_value(item) for item in value if _stringify_export_value(item))
    if isinstance(value, dict):
        for key in ("value", "label", "title", "name", "text", "content", "@value", "id", "@id", "url"):
            text = _stringify_export_value(value.get(key))
            if text:
                return text
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _schema_for_export_source(source: str) -> Optional[SourceSchema]:
    if source == "boalch":
        return BOALCH_SCHEMA
    if source == "philharmonie":
        return PHILHARMONIE_SCHEMA
    if source == "carmentis":
        return CARMENTIS_SCHEMA
    return None


def _parse_boalch_detail_page(url: str, soup: BeautifulSoup, raw_html: str) -> Record:
    pairs = _extract_label_value_pairs(soup, source="boalch")
    pairs = _clean_boalch_pairs(pairs)
    page_text = _page_text(soup)
    title = _clean_boalch_title(_best_page_title(soup))
    maker = _first_pair(pairs, "Maker")
    date = _first_pair(pairs, "Date", "Date Notes")
    object_name = _first_pair(pairs, "Instrument", "Object Type") or _infer_object_name(page_text)
    collection = _first_pair(pairs, "Present Owner", "Collection Details")
    location = _first_pair(pairs, "Instrument Location", "Location")
    catalog_number = _first_pair(pairs, "Catalog Number", "Inventory Number", "Serial Number", "Serial Number Notes")
    description = _join_non_empty(
        _first_pair(pairs, "Remarks"),
        _first_pair(pairs, "Description"),
        _first_pair(pairs, "Notes about Attribution"),
        _first_pair(pairs, "Provenance and Episodes"),
    )

    if not any([maker, date, collection, location, catalog_number, description]):
        raise ValueError("Boalch page did not expose enough record data to extract safely.")

    if _is_generic_title(title) and (maker or date or catalog_number):
        bits = [object_name or "Instrument"]
        if maker:
            bits.append(maker)
        if date:
            bits.append(date)
        if catalog_number:
            bits.append(f"catalog {catalog_number}")
        title = " - ".join(bits)

    metadata = {
        "title": title,
        "maker": maker,
        "date": date,
        "object_name": object_name,
        "location": location,
        "description": description,
        "inventory_number": catalog_number,
        "collection": collection,
        "source_specific": pairs,
    }
    metadata = {k: v for k, v in metadata.items() if v}
    object_id = url.rstrip("/").split("/")[-1] or title
    return Record(
        object_id=object_id,
        source="boalch",
        title=title,
        metadata=metadata,
        image_url=_first_content_image(soup, url),
        source_url=url,
        raw={"html_excerpt": raw_html[:20000], "parsed_pairs": pairs, "user_provided_url": True},
        retrieval_class="non_api_curated",
        is_semantic_anchor=False,
        source_type=SOURCE_REGISTRY["boalch"]["type"],
        source_schema=BOALCH_SCHEMA,
        evidence_spans=_pairs_to_spans(pairs),
    )


def _clean_boalch_title(title: str) -> str:
    title = " ".join((title or "").split())
    if _skip_extraction_value(title, source="boalch") or len(title) > 180:
        return "Instrument profile"
    return title


def _parse_philharmonie_detail_page(url: str, soup: BeautifulSoup, raw_html: str) -> Record:
    pairs = _extract_label_value_pairs(soup, source="philharmonie")
    page_text = _page_text(soup)
    header = _extract_philharmonie_header(soup)
    title = header.get("title") or _best_page_title(soup)
    maker = _first_pair(pairs, "Maker", "Maker / Author", "Author", "Auteur", "Facteur") or header.get("maker")
    date = _first_pair(pairs, "Date") or header.get("date")
    object_name = _first_pair(pairs, "Object Type", "Instrument", "Type") or _infer_object_name(title) or _infer_object_name(page_text)
    collection = _first_pair(pairs, "Collection")
    location = _first_pair(pairs, "Location", "Lieu", "Lieu de fabrication") or header.get("place")
    inventory_number = _first_pair(pairs, "Inventory Number", "Catalog Number", "Numéro d'inventaire", "Numero d'inventaire") or header.get("inventory_number")
    materials = _first_pair(pairs, "Materials", "Material", "Matériaux", "Materiaux")
    description = _join_non_empty(_first_pair(pairs, "Description"), _first_pair(pairs, "Remarks"), _first_pair(pairs, "Historique"))
    dimensions = _first_pair(pairs, "Dimensions")
    extent = _first_pair(pairs, "Étendue", "Etendue", "Compass")
    marks = _first_pair(pairs, "Marques et inscriptions", "Marks")
    decoration = _first_pair(pairs, "Décor", "Decor")
    history = _first_pair(pairs, "Historique")
    museum_location = _first_pair(pairs, "Localisation au Musée", "Localisation au Musee")
    books = _first_pair(pairs, "Livre(s)")
    articles = _first_pair(pairs, "Article(s)")
    documentation = _join_non_empty(books, articles)

    metadata = {
        "title": title,
        "maker": maker,
        "date": date,
        "object_name": object_name,
        "location": location,
        "description": description,
        "materials": materials,
        "inventory_number": inventory_number,
        "collection": collection,
        "dimensions": dimensions,
        "extent": extent,
        "marks": marks,
        "decoration": decoration,
        "history": history,
        "museum_location": museum_location,
        "production_place": header.get("place"),
        "documentation": documentation,
        "source_specific": {
            **pairs,
            **{f"header_{key}": value for key, value in header.items() if value},
        },
    }
    metadata = {k: v for k, v in metadata.items() if v}
    object_id = inventory_number or url.rstrip("/").split("/")[-1] or title
    return Record(
        object_id=object_id,
        source="philharmonie",
        title=title,
        metadata=metadata,
        image_url=_first_content_image(soup, url),
        source_url=url,
        raw={"html_excerpt": raw_html[:20000], "parsed_pairs": pairs, "user_provided_url": True},
        retrieval_class="non_api_curated",
        is_semantic_anchor=False,
        source_type=SOURCE_REGISTRY["philharmonie"]["type"],
        source_schema=PHILHARMONIE_SCHEMA,
        evidence_spans=_pairs_to_spans(pairs),
    )


def _parse_carmentis_detail_page(url: str, soup: BeautifulSoup, raw_html: str) -> Record:
    pairs = _extract_label_value_pairs(soup, source="carmentis")
    title = _first_pair(pairs, "Title", "Titel", "Titre", "Object name", "Objectnaam", "Dénomination", "Denomination") or _best_page_title(soup)
    object_name = _first_pair(pairs, "Object name", "Objectnaam", "Dénomination", "Denomination", "Object Type", "Type") or _infer_object_name(title)
    maker = _first_pair(pairs, "Artist/Maker", "Maker", "Creator", "Auteur", "Vervaardiger", "Author")
    date = _first_pair(pairs, "Date", "Dating", "Datering", "Datation")
    materials = _first_pair(pairs, "Material", "Materials", "Materiaal", "Matériaux", "Materiaux", "Technique", "Techniek")
    dimensions = _first_pair(pairs, "Dimensions", "Afmetingen")
    inventory_number = _first_pair(pairs, "Inventory number", "Inventarisnummer", "Numéro d'inventaire", "Numero d'inventaire", "Object number", "Objectnummer")
    collection = _first_pair(pairs, "Collection", "Department", "Département", "Departement")
    location = _first_pair(pairs, "Location", "Place", "Lieu", "Plaats")
    description = _first_pair(pairs, "Description", "Beschrijving", "Remarks", "Commentaire")

    if _is_generic_title(title):
        title = object_name or inventory_number or f"Carmentis object {_carmentis_object_id(url) or ''}".strip()
    if not any([title, object_name, maker, date, materials, inventory_number, description]):
        raise ValueError("Carmentis page did not expose enough record data to extract safely.")

    metadata = {
        "title": title,
        "maker": maker,
        "date": date,
        "object_name": object_name,
        "location": location,
        "description": description,
        "materials": materials,
        "dimensions": dimensions,
        "inventory_number": inventory_number,
        "collection": collection,
        "source_specific": pairs,
    }
    metadata = {k: v for k, v in metadata.items() if v}
    object_id = inventory_number or _carmentis_object_id(url) or url.rstrip("/").split("/")[-1] or title
    return Record(
        object_id=object_id,
        source="carmentis",
        title=title,
        metadata=metadata,
        image_url=_first_content_image(soup, url),
        source_url=url,
        raw={"html_excerpt": raw_html[:20000], "parsed_pairs": pairs, "user_provided_url": True},
        retrieval_class="non_api_curated",
        is_semantic_anchor=False,
        source_type=SOURCE_REGISTRY["carmentis"]["type"],
        source_schema=CARMENTIS_SCHEMA,
        evidence_spans=_pairs_to_spans(pairs),
    )


def _extract_label_value_pairs(soup: BeautifulSoup, source: Optional[str] = None) -> Dict[str, Any]:
    pairs: Dict[str, Any] = {}
    soup = BeautifulSoup(str(soup), "html.parser")

    for bad in soup(["script", "style", "noscript", "svg", "canvas"]):
        bad.decompose()
    for bad in soup.select(
        "nav, footer, form, button, input, select, textarea, "
        ".modal, .dialog, .popup, .popover, .tooltip, .dropdown-menu, "
        "[role='dialog'], [aria-hidden='true'], [hidden]"
    ):
        bad.decompose()
    for element in soup.select("[style]"):
        style = (element.get("style") or "").replace(" ", "").lower()
        if "display:none" in style or "visibility:hidden" in style:
            element.decompose()

    for row in soup.select("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
        if len(cells) >= 2:
            _add_pair(pairs, cells[0], " ".join(cells[1:]), source=source)

    for dt in soup.find_all("dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            _add_pair(pairs, dt.get_text(" ", strip=True), dd.get_text(" ", strip=True), source=source)

    lines = _visible_lines(soup)
    known = {_normalize_label(label) for label in KNOWN_DETAIL_LABELS | SECTION_LABELS}
    idx = 0
    while idx < len(lines):
        label = lines[idx]
        normalized = _normalize_label(label)
        if normalized in known:
            values = []
            idx += 1
            while idx < len(lines) and _normalize_label(lines[idx]) not in known:
                if not _skip_extraction_line(lines[idx], source=source):
                    values.append(lines[idx])
                idx += 1
            if _normalize_label(label) not in {_normalize_label(section) for section in SECTION_LABELS}:
                _add_pair(pairs, label, " ".join(values), source=source)
            continue
        idx += 1

    return pairs


def _extract_philharmonie_header(soup: BeautifulSoup) -> Dict[str, str]:
    """
    Extract the unlabelled summary block common on Cité de la musique pages.

    Typical order:
        title
        maker
        date
        place
        inventory number
    """
    lines = []
    for line in _visible_lines(soup):
        if _skip_philharmonie_header_line(line):
            continue
        lines.append(line)

    header: Dict[str, str] = {}
    for idx, line in enumerate(lines[:30]):
        norm = _normalize_label(line)
        if "title" not in header and not _looks_like_date(line) and not _looks_like_inventory_number(line):
            header["title"] = line
            continue
        if "maker" not in header and _looks_like_maker_line(line):
            header["maker"] = line
            continue
        if "date" not in header and _looks_like_date(line):
            header["date"] = line
            continue
        if "place" not in header and idx > 0 and norm not in {"description", "documentation"} and _looks_like_place_line(line):
            header["place"] = line
            continue
        if "inventory_number" not in header and _looks_like_inventory_number(line):
            header["inventory_number"] = line
            continue
        if len(header) >= 5:
            break
    return header


def _skip_philharmonie_header_line(line: str) -> bool:
    norm = _normalize_label(line)
    if not norm:
        return True
    if norm.startswith("photo "):
        return True
    return norm in {
        "vues",
        "description",
        "documentation",
        "livres",
        "articles",
        "photo",
    }


def _looks_like_maker_line(line: str) -> bool:
    lower = line.lower()
    return "," in line or "siècle" in lower or "siecle" in _strip_accents(lower)


def _looks_like_date(line: str) -> bool:
    return bool(re.search(r"\b(1[4-9]\d{2}|20\d{2})\b", line or ""))


def _looks_like_inventory_number(line: str) -> bool:
    return bool(re.search(r"\b[A-Z]\.[0-9A-Z]+(?:\.[0-9A-Z]+)+\b", line or ""))


def _looks_like_place_line(line: str) -> bool:
    if len(line) > 60 or any(char.isdigit() for char in line):
        return False
    norm = _normalize_label(line)
    known_places = {"paris", "bruxelles", "brussels", "londres", "london", "rome", "italie", "france", "belgique"}
    return norm in known_places or "/" in line or line.istitle()


def _add_pair(pairs: Dict[str, Any], label: str, value: str, source: Optional[str] = None) -> None:
    label = (label or "").strip(" :\n\t")
    value = _clean_extracted_value(label, value, source=source)
    if not label or not value or label == value:
        return
    if _skip_extraction_label(label, source=source) or _skip_extraction_value(value, source=source):
        return
    existing = pairs.get(label)
    if existing and value not in str(existing):
        pairs[label] = f"{existing} | {value}"
    elif not existing:
        pairs[label] = value


def _clean_boalch_pairs(pairs: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for label, value in pairs.items():
        if _skip_extraction_label(label, source="boalch"):
            continue
        value = _clean_extracted_value(label, str(value), source="boalch")
        if _skip_extraction_value(value, source="boalch"):
            continue
        cleaned[label] = value
    return cleaned


def _clean_extracted_value(label: str, value: str, source: Optional[str] = None) -> str:
    value = " ".join((value or "").split())
    if source == "boalch":
        for marker in (
            "Please Upload more or better photos",
            "Full Size Photo Viewer",
            "Navigate Return to List",
            "Online Resources",
            "Edit Links",
            "Edit Instrument Hyperlinks",
            "Edit CitBib Entries",
            "Warning: edits to this entry",
        ):
            idx = value.lower().find(marker.lower())
            if idx > 0:
                value = value[:idx].strip(" |:-")
        normalized_label = _normalize_label(label)
        if normalized_label in {"maker", "date", "location", "instrument location", "collection details"} and len(value) > 240:
            return ""
    return value


def _skip_extraction_label(label: str, source: Optional[str] = None) -> bool:
    normalized = _normalize_label(label)
    if source == "boalch":
        return normalized in {_normalize_label(item) for item in BOALCH_NON_DATA_LABELS}
    return False


def _skip_extraction_line(line: str, source: Optional[str] = None) -> bool:
    if _skip_extraction_label(line, source=source):
        return True
    return _skip_extraction_value(line, source=source)


def _skip_extraction_value(value: str, source: Optional[str] = None) -> bool:
    value = " ".join((value or "").split())
    if not value:
        return True
    lower = value.lower()
    if source == "boalch":
        if any(marker in lower for marker in BOALCH_BOILERPLATE_MARKERS):
            return True
        if len(value) > 900:
            return True
        if value in {"-", "--", "Serial#", "Serial No.", "No online resources available"}:
            return True
    return False


def _first_pair(pairs: Dict[str, Any], *labels: str) -> Optional[str]:
    normalized = {_normalize_label(key): value for key, value in pairs.items()}
    for label in labels:
        value = normalized.get(_normalize_label(label))
        if value:
            return str(value)
    return None


def _visible_lines(soup: BeautifulSoup) -> List[str]:
    return [line.strip() for line in soup.get_text("\n", strip=True).splitlines() if line.strip()]


def _page_text(soup: BeautifulSoup) -> str:
    return " ".join(_visible_lines(soup))


def _best_page_title(soup: BeautifulSoup) -> str:
    for selector in ("h1", "h2", ".title", "[data-title]"):
        element = soup.select_one(selector)
        if element:
            text = element.get_text(" ", strip=True)
            if text:
                return text
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return "Unknown"


def _is_generic_title(title: str) -> bool:
    lower = (title or "").lower()
    return not lower or lower in {"unknown", "instrument profile"} or "instrumentprofile" in lower.replace(" ", "")


def _infer_object_name(text: str) -> Optional[str]:
    lower = (text or "").lower()
    for candidate in ("harpsichord", "clavichord", "spinet", "virginal", "piano", "organ"):
        if candidate in lower:
            return candidate
    return None


def _first_content_image(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if not src:
            continue
        src_l = src.lower()
        if any(skip in src_l for skip in ("logo", "icon", "spinner", "blank")):
            continue
        return urljoin(base_url, src)
    return None


def _carmentis_object_id(url: str) -> Optional[str]:
    try:
        query = parse_qs(urlparse(url or "").query)
        values = query.get("objectId") or query.get("objectid")
        return values[0] if values else None
    except Exception:
        return None


def _pairs_to_spans(pairs: Dict[str, Any]) -> List[str]:
    return [f"{label}: {value}" for label, value in pairs.items() if value]


def _join_non_empty(*values: Optional[str]) -> Optional[str]:
    parts = []
    for value in values:
        if value and value not in parts:
            parts.append(value)
    return " | ".join(parts) if parts else None


def _normalize_label(label: str) -> str:
    stripped = _strip_accents(label or "")
    stripped = stripped.replace(":", "").replace("’", "'")
    stripped = re.sub(r"[^a-zA-Z0-9()/' -]+", " ", stripped)
    return " ".join(stripped.strip().lower().split())


def _strip_accents(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", value or "")
        if not unicodedata.combining(char)
    )


def search_boalch(query: str, rows: int = 10) -> List[Record]:
    """
    Attempt to search Boalch–Mould Online (boalch.org).

    The Boalch–Mould Online database is a specialized resource for keyboard instruments.
    We attempt light scraping with polite behavior. If blocked or unavailable, return [].

    Returns:
        List[Record]: Records found, or [] on failure
    """
    out: List[Record] = []
    if not (query or "").strip():
        return out

    # Check robots.txt
    if not _check_robots_txt("boalch.org"):
        logger.info("Boalch robots.txt suggests not scraping. Trying fallback dataset only.")
        return load_manual_dataset("boalch", "boalch")

    try:
        # Try search endpoint
        search_url = "https://www.boalch.org/search"
        params = {"q": query, "limit": rows}
        
        res = SESSION.get(search_url, params=params, timeout=15)
        res.raise_for_status()

        soup = BeautifulSoup(res.text, "html.parser")
        
        # Look for result items (adapt selector based on actual HTML structure)
        result_items = soup.select("[data-item], .result-item, .search-result")
        
        for item in result_items[:rows]:
            try:
                title = item.select_one("[data-title], .title, h3")
                if not title:
                    continue
                title_text = title.get_text(strip=True)
                
                # Extract metadata from item
                maker = None
                maker_elem = item.select_one("[data-maker], .maker")
                if maker_elem:
                    maker = maker_elem.get_text(strip=True)
                
                date = None
                date_elem = item.select_one("[data-date], .date")
                if date_elem:
                    date = date_elem.get_text(strip=True)
                
                location = None
                location_elem = item.select_one("[data-location], .location, .collection")
                if location_elem:
                    location = location_elem.get_text(strip=True)
                
                object_name = None
                type_elem = item.select_one("[data-type], .type, .object-type")
                if type_elem:
                    object_name = type_elem.get_text(strip=True)
                
                description = None
                desc_elem = item.select_one("[data-description], .description, .summary")
                if desc_elem:
                    description = desc_elem.get_text(strip=True)
                
                url = None
                link = item.select_one("a")
                if link and link.get("href"):
                    url = urljoin("https://www.boalch.org/", link["href"])
                
                # Build Record object
                object_id = url.split("/")[-1] if url else title_text.replace(" ", "_")
                
                metadata = {
                    "title": title_text,
                    "maker": maker,
                    "date": date,
                    "location": location,
                    "object_name": object_name,
                    "description": description,
                }
                metadata = {k: v for k, v in metadata.items() if v}
                
                rec = Record(
                    object_id=object_id,
                    source="boalch",
                    title=title_text,
                    metadata=metadata,
                    image_url=None,
                    source_url=url,
                    raw={"search_result": str(item)},
                    retrieval_class="non_api_curated",
                    is_semantic_anchor=False,
                    source_type="authority_database",
                    source_schema=BOALCH_SCHEMA,
                )
                out.append(rec)
            except Exception as inner_exc:
                logger.debug(f"Boalch item parsing failed: {inner_exc}")
                continue

    except Exception as exc:
        logger.warning(f"Boalch search failed: {exc}. Falling back to manual dataset if available.")
        return load_manual_dataset("boalch", "boalch")

    return out


def search_philharmonie(query: str, rows: int = 10) -> List[Record]:
    """
    Attempt to search Philharmonie de Paris Museum Collections.

    Strategy:
    - Check robots.txt
    - Try to find search/collection API or embedded JSON
    - Parse result cards
    - Extract title, maker, date, image, etc.
    - Return Record objects or fallback to manual dataset

    Returns:
        List[Record]: Records found, or [] on failure
    """
    out: List[Record] = []
    if not (query or "").strip():
        return out

    # Check robots.txt
    if not _check_robots_txt("collectionsdumusee.philharmoniedeparis.fr"):
        logger.info("Philharmonie robots.txt suggests not scraping. Trying fallback dataset only.")
        return load_manual_dataset("philharmonie", "philharmonie")

    try:
        search_url = "https://collectionsdumusee.philharmoniedeparis.fr/search"
        params = {"q": query, "limit": rows}
        
        res = SESSION.get(search_url, params=params, timeout=15)
        res.raise_for_status()

        soup = BeautifulSoup(res.text, "html.parser")
        
        # Look for result items
        result_items = soup.select("[data-item], .result-item, .collection-item, [class*='result']")
        
        for item in result_items[:rows]:
            try:
                title = item.select_one("[data-title], .title, h3, h2")
                if not title:
                    continue
                title_text = title.get_text(strip=True)
                
                # Extract metadata
                maker = None
                maker_elem = item.select_one("[data-maker], .maker, .artist, .creator")
                if maker_elem:
                    maker = maker_elem.get_text(strip=True)
                
                date = None
                date_elem = item.select_one("[data-date], .date, .year")
                if date_elem:
                    date = date_elem.get_text(strip=True)
                
                object_name = None
                type_elem = item.select_one("[data-type], .type, .object-type, .classification")
                if type_elem:
                    object_name = type_elem.get_text(strip=True)
                
                description = None
                desc_elem = item.select_one("[data-description], .description, .summary")
                if desc_elem:
                    description = desc_elem.get_text(strip=True)
                
                image_url = None
                img = item.select_one("img")
                if img and img.get("src"):
                    img_src = urljoin("https://collectionsdumusee.philharmoniedeparis.fr/", img["src"])
                    image_url = img_src
                
                location = None
                location_elem = item.select_one("[data-location], .location, .collection, .inventory")
                if location_elem:
                    location = location_elem.get_text(strip=True)
                
                url = None
                link = item.select_one("a")
                if link and link.get("href"):
                    url = urljoin("https://collectionsdumusee.philharmoniedeparis.fr/", link["href"])
                
                object_id = url.split("/")[-1] if url else title_text.replace(" ", "_")
                
                metadata = {
                    "title": title_text,
                    "maker": maker,
                    "date": date,
                    "object_name": object_name,
                    "description": description,
                    "location": location,
                }
                metadata = {k: v for k, v in metadata.items() if v}
                
                rec = Record(
                    object_id=object_id,
                    source="philharmonie",
                    title=title_text,
                    metadata=metadata,
                    image_url=image_url,
                    source_url=url,
                    raw={"search_result": str(item)},
                    retrieval_class="non_api_curated",
                    is_semantic_anchor=False,
                    source_type="museum_collection",
                    source_schema=PHILHARMONIE_SCHEMA,
                )
                out.append(rec)
            except Exception as inner_exc:
                logger.debug(f"Philharmonie item parsing failed: {inner_exc}")
                continue

    except Exception as exc:
        logger.warning(f"Philharmonie search failed: {exc}. Falling back to manual dataset if available.")
        return load_manual_dataset("philharmonie", "philharmonie")

    return out


def load_manual_dataset(path: str, source: str) -> List[Record]:
    """
    Load manually curated dataset for non-API sources.
    Used when scraping is unavailable, blocked, or manually curated data is preferred.

    If path points to an existing file, load it directly. Otherwise look for
    data/{source}_{path}.json/jsonl/csv and data/{source}.json/jsonl/csv.

    JSON format:
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

    JSONL format: one record per line

    Args:
        path: explicit file path or fallback dataset identifier
        source: source name (e.g., "boalch", "philharmonie")

    Returns:
        List[Record]: Records loaded from dataset, or [] if not found
    """
    out: List[Record] = []
    
    from src.settings import DATA_DIR
    
    direct = Path(path)
    candidates = [direct] if direct.exists() else [
        DATA_DIR / f"{source}_{path}.json",
        DATA_DIR / f"{source}_{path}.jsonl",
        DATA_DIR / f"{source}_{path}.csv",
        DATA_DIR / f"{source}.json",
        DATA_DIR / f"{source}.jsonl",
        DATA_DIR / f"{source}.csv",
    ]
    
    for path in candidates:
        if not path.exists():
            continue
        
        try:
            if path.suffix == ".jsonl":
                # JSONL format: one record per line
                with open(path, "r") as f:
                    for line in f:
                        if line.strip():
                            record_data = json.loads(line)
                            rec = _build_record_from_dataset_entry(source, record_data)
                            if rec:
                                out.append(rec)
            elif path.suffix == ".csv":
                with open(path, "r", newline="") as f:
                    for record_data in csv.DictReader(f):
                        rec = _build_record_from_dataset_entry(source, record_data)
                        if rec:
                            out.append(rec)
            else:
                # JSON format
                with open(path, "r") as f:
                    data = json.load(f)
                    records = data.get("records", []) if isinstance(data, dict) else data
                    for record_data in records:
                        rec = _build_record_from_dataset_entry(source, record_data)
                        if rec:
                            out.append(rec)
            
            logger.info(f"Loaded {len(out)} records from {path}")
            return out
        except Exception as e:
            logger.debug(f"Failed to load {path}: {e}")
            continue
    
    logger.info(f"No manual dataset found for {source}. Returning empty list.")
    return []


def _build_record_from_dataset_entry(source: str, entry: Dict[str, Any]) -> Optional[Record]:
    """
    Convert a dataset entry to a Record object.
    """
    try:
        title = entry.get("title") or entry.get("name") or "Unknown"
        object_id = entry.get("object_id") or entry.get("id") or title
        
        metadata = {
            "title": title,
            "maker": entry.get("maker") or entry.get("artist") or entry.get("creator"),
            "date": entry.get("date") or entry.get("year"),
            "object_name": entry.get("object_name") or entry.get("type") or entry.get("classification"),
            "description": entry.get("description") or entry.get("summary"),
            "location": entry.get("location") or entry.get("collection") or entry.get("place"),
        }
        metadata = {k: v for k, v in metadata.items() if v}
        
        source_type = "authority_database" if source == "boalch" else "museum_collection"
        schema = {
            "boalch": BOALCH_SCHEMA,
            "philharmonie": PHILHARMONIE_SCHEMA,
            "carmentis": CARMENTIS_SCHEMA,
        }.get(source, PHILHARMONIE_SCHEMA)
        
        return Record(
            object_id=str(object_id),
            source=source,
            title=title,
            metadata=metadata,
            image_url=entry.get("image_url") or entry.get("image"),
            source_url=entry.get("source_url") or entry.get("url"),
            raw={"dataset_entry": entry},
            retrieval_class="non_api_curated",
            is_semantic_anchor=False,
            source_type=source_type,
            source_schema=schema,
        )
    except Exception as e:
        logger.debug(f"Failed to build record from dataset entry: {e}")
        return None
