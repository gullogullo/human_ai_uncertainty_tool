"""Retrieval layer with explicit source schema exposure."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional
import requests

from src.models import Record, SourceSchema
from src.settings import (
    EUROPEANA_API,
    EUROPEANA_KEY,
    RIJKSMUSEUM_SEARCH_API,
    SOURCE_REGISTRY,
    THE_MET_API,
    VICTORIA_AND_ALBERT_API,
)

logger = logging.getLogger(__name__)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "REMAKE/0.5", "Accept": "application/json"})

EUROPEANA_SCHEMA = SourceSchema(
    source="europeana",
    schema_name="Europeana search payload (selected fields)",
    fields=["title", "description", "creator", "date", "subject"],
    field_groups={
        "title": "identification",
        "description": "description",
        "creator": "agents",
        "date": "time",
        "subject": "subject",
    },
)

THE_MET_SCHEMA = SourceSchema(
    source="the_met",
    schema_name="The Met object payload (selected fields)",
    fields=["title", "artist", "date", "department", "object_name", "medium", "credit_line"],
    field_groups={
        "title": "identification",
        "artist": "agents",
        "date": "time",
        "department": "administrative",
        "object_name": "classification",
        "medium": "material",
        "credit_line": "administrative",
    },
)

RIJKSMUSEUM_SCHEMA = SourceSchema(
    source="rijksmuseum",
    schema_name="Rijksmuseum resolver payload (selected fields)",
    fields=["title", "description", "creator", "date_created", "artform", "material"],
    field_groups={
        "title": "identification",
        "description": "description",
        "creator": "agents",
        "date_created": "time",
        "artform": "classification",
        "material": "material",
    },
)

VICTORIA_AND_ALBERT_SCHEMA = SourceSchema(
    source="victoria_and_albert",
    schema_name="V&A object search payload (selected fields)",
    fields=["title", "description", "maker", "date", "object_type", "material", "place"],
    field_groups={
        "title": "identification",
        "description": "description",
        "maker": "agents",
        "date": "time",
        "object_type": "classification",
        "material": "material",
        "place": "place",
    },
)


def _nested_get(value: Any, *path: str, default: Any = None) -> Any:
    current = value
    for key in path:
        if isinstance(current, dict):
            current = current.get(key, default)
        else:
            return default
        if current is default:
            return default
    return current


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value).strip()
    if isinstance(value, list):
        parts = [_normalize_text(v) for v in value]
        return " | ".join(part for part in parts if part)
    if isinstance(value, dict):
        for key in ("content", "value", "@value", "name", "_label", "label", "title", "id", "@id", "contentUrl", "thumbnailUrl", "url"):
            text = _normalize_text(value.get(key))
            if text:
                return text
        return ""
    return str(value).strip()


def _listify(value: Any) -> List[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _pick_first_text(*values: Any) -> str:
    for value in values:
        text = _normalize_text(value)
        if text:
            return text
    return ""


def _join_values(values: Iterable[Any]) -> Optional[str]:
    parts = []
    seen = set()
    for value in values:
        text = _normalize_text(value)
        if text and text not in seen:
            seen.add(text)
            parts.append(text)
    return " | ".join(parts) if parts else None


def _jsonld_values(value: Any) -> List[str]:
    values: List[str] = []
    for item in _listify(value):
        if isinstance(item, dict) and "@graph" in item:
            for graph_item in item.get("@graph", []):
                values.extend(_jsonld_values(graph_item))
            continue
        text = _normalize_text(item)
        if text:
            values.append(text)
    return values


def _extract_texts_from_vam_entities(value: Any) -> List[str]:
    values: List[str] = []
    for item in _listify(value):
        if isinstance(item, list):
            values.extend(_extract_texts_from_vam_entities(item))
            continue
        if isinstance(item, dict):
            text = _pick_first_text(
                _nested_get(item, "text"),
                _nested_get(item, "title"),
                _nested_get(item, "name", "text"),
                _nested_get(item, "date", "text"),
                _nested_get(item, "place", "text"),
                _nested_get(item, "association", "text"),
            )
            if text:
                values.append(text)
                continue
        text = _normalize_text(item)
        if text:
            values.append(text)
    return values


def _vam_title_from_record(record: Dict[str, Any]) -> str:
    titles = _listify(record.get("titles"))
    for item in titles:
        if isinstance(item, dict):
            title = _pick_first_text(item.get("title"), item.get("text"))
            if title:
                return title
    return _pick_first_text(record.get("_primaryTitle"), record.get("title")) or "Unknown"


def _resolve_rijksmuseum_object(identifier: str) -> Optional[Dict[str, Any]]:
    try:
        res = SESSION.get(
            identifier,
            params={"_profile": "schema", "_mediatype": "application/ld+json"},
            headers={"Accept": "application/ld+json"},
            timeout=20,
        )
        res.raise_for_status()
        return res.json()
    except Exception as exc:
        logger.debug("Rijksmuseum resolver fetch failed for %s: %s", identifier, exc)
        return None


def _select_rijksmuseum_resource(payload: Any, identifier: str) -> Dict[str, Any]:
    candidates = []
    if isinstance(payload, dict) and "@graph" in payload:
        candidates = [item for item in payload.get("@graph", []) if isinstance(item, dict)]
    elif isinstance(payload, list):
        candidates = [item for item in payload if isinstance(item, dict)]
    elif isinstance(payload, dict):
        candidates = [payload]

    for item in candidates:
        if _normalize_text(item.get("@id")) == identifier:
            return item
    for item in candidates:
        if item.get("@type") in {"VisualArtwork", "CreativeWork", "HumanMadeObject"}:
            return item
    return candidates[0] if candidates else {}


def _build_rijksmuseum_image_url(resource: Dict[str, Any]) -> Optional[str]:
    image = resource.get("image")
    if isinstance(image, dict):
        return _pick_first_text(image.get("contentUrl"), image.get("url"), image.get("@id"))
    if isinstance(image, list):
        for item in image:
            if isinstance(item, dict):
                url = _pick_first_text(item.get("contentUrl"), item.get("url"), item.get("@id"))
                if url:
                    return url
    return _normalize_text(image) or None


def _parse_rijksmuseum_record(query: str, identifier: str, payload: Any) -> Optional[Record]:
    resource = _select_rijksmuseum_resource(payload, identifier)
    if not resource:
        return None

    title = _pick_first_text(resource.get("name"), resource.get("headline")) or "Unknown"
    metadata = {
        "title": title,
        "description": _join_values(_jsonld_values(resource.get("description"))),
        "creator": _join_values(_jsonld_values(resource.get("creator"))),
        "date_created": _join_values(_jsonld_values(resource.get("dateCreated"))),
        "artform": _join_values(_jsonld_values(resource.get("artform"))) or _join_values(_jsonld_values(resource.get("additionalType"))),
        "material": _join_values(_jsonld_values(resource.get("material"))),
    }
    metadata = {k: v for k, v in metadata.items() if v}
    retrieval_class = infer_retrieval_class(query, title, metadata, "rijksmuseum")
    metadata["retrieval_class"] = retrieval_class

    source_url = _pick_first_text(resource.get("url"), identifier)
    object_id = identifier.rstrip("/").split("/")[-1]

    return Record(
        object_id=object_id or identifier,
        source="rijksmuseum",
        title=title,
        metadata=metadata,
        image_url=_build_rijksmuseum_image_url(resource),
        source_url=source_url or identifier,
        raw=payload if isinstance(payload, dict) else {"payload": payload},
        retrieval_class=retrieval_class,
        is_semantic_anchor=False,
        source_schema=RIJKSMUSEUM_SCHEMA,
    )


def _vam_image_url(record: Dict[str, Any]) -> Optional[str]:
    images = record.get("_images") if isinstance(record.get("_images"), dict) else {}
    thumbnail = _normalize_text(images.get("_primary_thumbnail"))
    if thumbnail:
        return thumbnail
    iiif_base = _normalize_text(images.get("_iiif_image_base_url"))
    if iiif_base:
        return f"{iiif_base.rstrip('/')}/full/full/0/default.jpg"
    return None


def _fetch_vam_object(system_number: str) -> Optional[Dict[str, Any]]:
    endpoints = [
        f"{VICTORIA_AND_ALBERT_API}/objects/{system_number}",
        f"{VICTORIA_AND_ALBERT_API}/museumobject/{system_number}",
    ]
    for endpoint in endpoints:
        try:
            res = SESSION.get(endpoint, timeout=20)
            if res.status_code == 404:
                continue
            res.raise_for_status()
            payload = res.json()
            record = payload.get("record") if isinstance(payload, dict) else None
            if isinstance(record, dict):
                return record
        except Exception as exc:
            logger.debug("V&A object fetch failed for %s via %s: %s", system_number, endpoint, exc)
    return None


def _parse_vam_record(query: str, summary_record: Dict[str, Any], detail_record: Optional[Dict[str, Any]] = None) -> Record:
    base = detail_record if isinstance(detail_record, dict) else summary_record
    title = _vam_title_from_record(base)

    maker_values = []
    for field_name in ("artistMakerPerson", "artistMakerPeople", "artistMakerOrganisations"):
        maker_values.extend(_extract_texts_from_vam_entities(base.get(field_name)))
    if not maker_values:
        maker_values.extend(_extract_texts_from_vam_entities(summary_record.get("_primaryMaker")))

    date_values = _extract_texts_from_vam_entities(base.get("productionDates"))
    if not date_values:
        date_values.extend(_extract_texts_from_vam_entities(summary_record.get("_primaryDate")))

    material = _pick_first_text(
        base.get("materialsAndTechniques"),
        _join_values(_extract_texts_from_vam_entities(base.get("materials"))),
        _pick_first_text(summary_record.get("_sampleMaterial"), summary_record.get("materials")),
    )

    place = _pick_first_text(
        _join_values(_extract_texts_from_vam_entities(base.get("placesOfOrigin"))),
        summary_record.get("_primaryPlace"),
    )

    object_type = _pick_first_text(
        base.get("objectType"),
        summary_record.get("objectType"),
    )

    description = _pick_first_text(
        base.get("summaryDescription"),
        summary_record.get("summaryDescription"),
        summary_record.get("summary"),
    )

    metadata = {
        "title": title,
        "description": description,
        "maker": _join_values(maker_values),
        "date": _join_values(date_values),
        "object_name": object_type,
        "materials": material,
        "location": place,
    }
    metadata = {k: v for k, v in metadata.items() if v}
    retrieval_class = infer_retrieval_class(query, title, metadata, "victoria_and_albert")
    metadata["retrieval_class"] = retrieval_class

    system_number = _pick_first_text(summary_record.get("systemNumber"), base.get("systemNumber"), summary_record.get("id"), summary_record.get("pk"))
    raw_payload = {"search_record": summary_record}
    if detail_record:
        raw_payload["detail_record"] = detail_record

    return Record(
        object_id=system_number or title,
        source="victoria_and_albert",
        title=title,
        metadata=metadata,
        image_url=_vam_image_url(summary_record),
        source_url=(f"https://collections.vam.ac.uk/item/{system_number}/" if system_number else None),
        raw=raw_payload,
        retrieval_class=retrieval_class,
        is_semantic_anchor=False,
        source_schema=VICTORIA_AND_ALBERT_SCHEMA,
        source_type=SOURCE_REGISTRY["victoria_and_albert"]["type"],
    )

def infer_retrieval_class(query: str, title: str, metadata: Dict[str, object], source: str) -> str:
    q = (query or "").lower().strip()
    title_l = (title or "").lower()

    if q and q == title_l:
        return "exact_title_match"
    if q and q in title_l:
        return "title_match"

    aliases = metadata.get("aliases_en")
    if isinstance(aliases, list):
        aliases_l = [str(a).lower() for a in aliases]
        if q and any(q in a for a in aliases_l):
            return "alias_match"

    desc = str(metadata.get("description", "")).lower()
    if q and q in desc:
        return "description_match"

    subj = str(metadata.get("subject", "")).lower()
    if q and q in subj:
        return "subject_match"

    return "retrieval_match"

def search_europeana(query: str, rows: int = 10) -> List[Record]:
    if not (query or "").strip():
        return []
    if not EUROPEANA_KEY:
        logger.warning("No Europeana API key found.")
        return []

    out: List[Record] = []
    try:
        res = SESSION.get(
            EUROPEANA_API,
            params={"query": query, "rows": rows, "profile": "rich", "wskey": EUROPEANA_KEY},
            timeout=20,
        )
        res.raise_for_status()
        data = res.json()
        for item in data.get("items", []):
            title = item.get("title", ["Unknown"])[0] if isinstance(item.get("title"), list) else item.get("title", "Unknown")
            metadata = {
                "title": title,
                "description": " ".join(item.get("dcDescription", [])) if item.get("dcDescription") else None,
                "maker": " ".join(item.get("dcCreator", [])) if item.get("dcCreator") else None,
                "date": " ".join(item.get("dcIssued", [])) if item.get("dcIssued") else None,
                "subject": " ".join(item.get("dcSubject", [])) if item.get("dcSubject") else None,
                "source_specific": {"europeana_api_url": item.get("link")} if item.get("link") else None,
            }
            metadata = {k: v for k, v in metadata.items() if v}
            retrieval_class = infer_retrieval_class(query, title, metadata, "europeana")
            metadata["retrieval_class"] = retrieval_class
            source_url = _pick_first_text(
                item.get("edmIsShownAt"),
                item.get("guid"),
                item.get("edmLandingPage"),
                item.get("link"),
            )
            out.append(
                Record(
                    object_id=item.get("id", ""),
                    source="europeana",
                    title=title,
                    metadata=metadata,
                    image_url=item.get("edmIsShownBy") or item.get("edmPreview"),
                    source_url=source_url,
                    raw=item,
                    retrieval_class=retrieval_class,
                    is_semantic_anchor=False,
                    source_schema=EUROPEANA_SCHEMA,
                    source_type=SOURCE_REGISTRY["europeana"]["type"],
                )
            )
    except Exception as exc:
        logger.error("Europeana search failed: %s", exc)
    return out

def search_the_met(query: str, rows: int = 10) -> List[Record]:
    if not (query or "").strip():
        return []
    out: List[Record] = []
    try:
        res = SESSION.get(f"{THE_MET_API}/search", params={"q": query}, timeout=20)
        res.raise_for_status()
        object_ids = (res.json().get("objectIDs") or [])[:rows]
        for object_id in object_ids:
            try:
                obj = SESSION.get(f"{THE_MET_API}/objects/{object_id}", timeout=20).json()
                title = obj.get("title", "Unknown")
                metadata = {
                    "title": title,
                    "maker": obj.get("artistDisplayName"),
                    "date": obj.get("objectDate"),
                    "object_name": obj.get("objectName"),
                    "materials": obj.get("medium"),
                    "collection": obj.get("department"),
                    "source_specific": {"credit_line": obj.get("creditLine")} if obj.get("creditLine") else None,
                }
                metadata = {k: v for k, v in metadata.items() if v}
                retrieval_class = infer_retrieval_class(query, title, metadata, "the_met")
                metadata["retrieval_class"] = retrieval_class
                out.append(
                    Record(
                        object_id=str(object_id),
                        source="the_met",
                        title=title,
                        metadata=metadata,
                        image_url=obj.get("primaryImageSmall"),
                        source_url=obj.get("objectURL", ""),
                        raw=obj,
                        retrieval_class=retrieval_class,
                        is_semantic_anchor=False,
                        source_schema=THE_MET_SCHEMA,
                        source_type=SOURCE_REGISTRY["the_met"]["type"],
                    )
                )
            except Exception as inner_exc:
                logger.debug("The Met object fetch failed for %s: %s", object_id, inner_exc)
    except Exception as exc:
        logger.error("The Met search failed: %s", exc)
    return out

def search_rijksmuseum(query: str, rows: int = 10) -> List[Record]:
    out: List[Record] = []
    seen_ids = set()
    search_attempts = [
        {"title": query, "imageAvailable": "true"},
        {"description": query, "imageAvailable": "true"},
        {"creator": query, "imageAvailable": "true"},
        {"type": query, "imageAvailable": "true"},
        {"material": query, "imageAvailable": "true"},
    ]

    try:
        for params in search_attempts:
            if len(seen_ids) >= rows:
                break
            res = SESSION.get(RIJKSMUSEUM_SEARCH_API, params=params, timeout=20)
            res.raise_for_status()
            ordered_items = _listify(res.json().get("orderedItems", []))
            for item in ordered_items:
                identifier = _normalize_text(item.get("id") if isinstance(item, dict) else item)
                if not identifier or identifier in seen_ids:
                    continue
                payload = _resolve_rijksmuseum_object(identifier)
                if not payload:
                    continue
                record = _parse_rijksmuseum_record(query, identifier, payload)
                if record:
                    out.append(record)
                    seen_ids.add(identifier)
                if len(out) >= rows:
                    break
    except Exception as exc:
        logger.error("Rijksmuseum search failed: %s", exc)
    return out

def search_victoria_and_albert(query: str, rows: int = 10) -> List[Record]:
    if not (query or "").strip():
        return []
    out: List[Record] = []
    try:
        res = SESSION.get(
            f"{VICTORIA_AND_ALBERT_API}/objects/search",
            params={"q": query, "page_size": rows},
            timeout=20,
        )
        res.raise_for_status()
        payload = res.json()
        records = _listify(payload.get("records", []))
        for item in records[:rows]:
            system_number = _pick_first_text(item.get("systemNumber"), item.get("id"), item.get("pk"))
            detail_record = _fetch_vam_object(system_number) if system_number else None
            out.append(_parse_vam_record(query, item, detail_record=detail_record))
    except Exception as exc:
        logger.error("Victoria & Albert search failed: %s", exc)
    return out

def search_all_sources(query: str, rows: int = 10) -> Dict[str, List[Record]]:
    from src.non_api_retrieval import search_boalch, search_philharmonie
    
    return {
        "europeana": search_europeana(query, rows=rows),
        "the_met": search_the_met(query, rows=rows),
        "victoria_and_albert": search_victoria_and_albert(query, rows=rows),
        "boalch": search_boalch(query, rows=rows),
        "philharmonie": search_philharmonie(query, rows=rows),
    }
