"""AI image interpretation layer for visual claim extraction and multimodal consistency checks."""

from __future__ import annotations

import logging
import base64
import os
from functools import lru_cache
from typing import Any, Dict, Optional, List
from pathlib import Path
from io import BytesIO

from src.models import Record
from src.fields import normalize_field_value

logger = logging.getLogger(__name__)


VISUAL_INDEX_LABELS = [
    {
        "label": "musical instrument",
        "claim_value": "musical instrument",
        "claim_type": "present_type",
        "prompts": [
            "a photo of a musical instrument",
            "a museum photograph of a musical instrument",
            "a historical keyboard or stringed musical instrument",
        ],
        "text_terms": ["instrument", "musical instrument", "harpsichord", "spinet", "piano", "violin", "organ"],
    },
    {
        "label": "keyboard instrument",
        "claim_value": "keyboard instrument",
        "claim_type": "present_type",
        "prompts": [
            "a photo of a keyboard musical instrument",
            "a harpsichord, spinet, piano, or organ with a keyboard",
            "a museum object with piano or harpsichord keys",
        ],
        "text_terms": ["keyboard", "harpsichord", "spinet", "piano", "organ", "clavier", "clavichord"],
    },
    {
        "label": "keyboard detail",
        "claim_value": "keyboard detail",
        "claim_type": "present_type",
        "prompts": [
            "a close up detail of keyboard keys",
            "a close-up photograph of piano or harpsichord keys",
            "a detail image of black and white musical keyboard keys",
        ],
        "text_terms": ["key", "keys", "keyboard", "manual", "compass"],
    },
    {
        "label": "book",
        "claim_value": "book",
        "claim_type": "present_type",
        "prompts": [
            "a photo of a book",
            "an open book or bound volume",
            "a digitized historical book page",
        ],
        "text_terms": ["book", "volume", "binding", "bound", "printed book"],
    },
    {
        "label": "printed text page",
        "claim_value": "printed text page",
        "claim_type": "description",
        "prompts": [
            "a page of printed text",
            "a digitized page with printed writing",
            "a printed document page",
        ],
        "text_terms": ["printed", "text", "page", "document", "publication", "book"],
    },
    {
        "label": "handwritten manuscript",
        "claim_value": "handwritten manuscript",
        "claim_type": "description",
        "prompts": [
            "a handwritten manuscript page",
            "a page with handwriting",
            "an archival handwritten document",
        ],
        "text_terms": ["manuscript", "handwritten", "autograph", "letter", "archive"],
    },
    {
        "label": "music score",
        "claim_value": "music score",
        "claim_type": "present_type",
        "prompts": [
            "a page of sheet music",
            "a music score with staff notation",
            "a musical score manuscript or printed score",
        ],
        "text_terms": ["score", "sheet music", "music", "notation", "staff", "partitur", "partition"],
    },
    {
        "label": "painting",
        "claim_value": "painting",
        "claim_type": "present_type",
        "prompts": [
            "a photo of a painting",
            "a framed painted artwork",
            "a museum painting on canvas or panel",
        ],
        "text_terms": ["painting", "painted", "oil", "canvas", "panel", "portrait"],
    },
    {
        "label": "inscription or label",
        "claim_value": "inscription or label",
        "claim_type": "description",
        "prompts": [
            "a close-up of an inscription or label",
            "a photograph of written labels or inscriptions on an object",
            "a detail image showing an inscription",
        ],
        "text_terms": ["inscription", "label", "signature", "signed", "marking", "nameboard"],
    },
    {
        "label": "decorative object detail",
        "claim_value": "decorative object detail",
        "claim_type": "description",
        "prompts": [
            "a close-up detail of decorative ornament",
            "a detail photograph of ornament on a museum object",
            "a decorative carved or painted detail",
        ],
        "text_terms": ["detail", "decoration", "ornament", "carved", "painted", "gilded"],
    },
]

_CLIP_MODEL_NAME = "ViT-B-32"
_CLIP_PRETRAINED = "laion2b_s34b_b79k"


def interpret_record_image(record: Record) -> dict:
    """
    Given a record with an image, return structured visual observations.

    This function attempts to use OpenAI Vision API if configured, otherwise returns
    a fallback structure. Never treats AI image interpretation as ground truth.

    Args:
        record: Record object with image_url or local_image_path

    Returns:
        dict: {
            "visible_object_type": "harpsichord",
            "visible_materials": ["wood", "ivory"],
            "visible_features": ["keyboard", "case", "decorated_lid"],
            "uncertain_observations": ["possibly gilded", "ornaments unclear"],
            "caption": "A decorated keyboard instrument...",
            "model": "openai_gpt4_vision",
            "confidence_note": "AI visual interpretation; requires human validation",
            "error": null or error message,
            "success": bool
        }
    """
    result = {
        "visible_object_type": None,
        "visible_materials": [],
        "visible_features": [],
        "uncertain_observations": [],
        "caption": None,
        "model": None,
        "confidence_note": "AI visual interpretation; requires human validation",
        "error": None,
        "success": False
    }

    # Determine image source
    image_url = record.image_url
    local_image_path = record.local_image_path

    if not image_url and not local_image_path:
        result["error"] = "No image available for this record"
        return result

    try:
        # Try OpenAI Vision API if configured
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            return _interpret_with_openai_vision(image_url, local_image_path, api_key)
        else:
            # Fallback: use CLIP or return basic structure
            logger.info("No OpenAI API key. Returning fallback image interpretation.")
            return _fallback_image_interpretation(record)
    except Exception as e:
        result["error"] = f"Image interpretation failed: {str(e)}"
        logger.warning(f"Image interpretation error: {e}")
        return result


def _interpret_with_openai_vision(
    image_url: Optional[str],
    local_image_path: Optional[str],
    api_key: str
) -> dict:
    """
    Use OpenAI GPT-4 Vision API to interpret an image.
    """
    try:
        import requests
    except ImportError:
        logger.warning("requests library not available for vision API")
        return _fallback_image_interpretation_empty()

    result = {
        "visible_object_type": None,
        "visible_materials": [],
        "visible_features": [],
        "uncertain_observations": [],
        "caption": None,
        "model": "openai_gpt4_vision",
        "confidence_note": "AI visual interpretation; requires human validation",
        "error": None,
        "success": False
    }

    # Prepare image data
    image_data = None
    if local_image_path:
        try:
            with open(local_image_path, "rb") as f:
                image_bytes = f.read()
                image_data = base64.standard_b64encode(image_bytes).decode("utf-8")
                # Infer media type from file extension
                ext = Path(local_image_path).suffix.lower()
                media_type = {
                    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"
                }.get(ext, "image/jpeg")
        except Exception as e:
            result["error"] = f"Failed to read local image: {e}"
            return result
    elif image_url:
        # Use URL directly
        image_data = image_url
        media_type = None
    else:
        result["error"] = "No image source"
        return result

    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        # Build message with image
        content = [
            {
                "type": "text",
                "text": """Analyze this cultural heritage object image. Provide:
1. visible_object_type: What type of object is visible? (e.g., harpsichord, violin, sculpture)
2. visible_materials: List visible materials (e.g., wood, metal, bone, ivory, paint)
3. visible_features: List observable design features (e.g., keyboard, strings, decorations, handle)
4. uncertain_observations: Note anything you're uncertain about, e.g., "ornament style unclear due to angle"
5. caption: A 1-2 sentence descriptive caption

Format your response as JSON:
{
  "visible_object_type": "...",
  "visible_materials": ["...", "..."],
  "visible_features": ["...", "..."],
  "uncertain_observations": ["...", "..."],
  "caption": "..."
}"""
            }
        ]

        if image_data:
            image_url_payload = f"data:{media_type};base64,{image_data}" if media_type else image_data
            content.append({
                "type": "image_url",
                "image_url": {"url": image_url_payload}
            })

        payload = {
            "model": os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini"),
            "messages": [
                {
                    "role": "user",
                    "content": content
                }
            ],
            "max_tokens": 1024,
            "temperature": 0.3
        }

        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()

        response_data = response.json()
        message_content = response_data.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Parse JSON response
        import json
        parsed = json.loads(message_content)

        result.update({
            "visible_object_type": parsed.get("visible_object_type"),
            "visible_materials": parsed.get("visible_materials", []),
            "visible_features": parsed.get("visible_features", []),
            "uncertain_observations": parsed.get("uncertain_observations", []),
            "caption": parsed.get("caption"),
            "success": True
        })

    except Exception as e:
        result["error"] = f"OpenAI Vision API call failed: {str(e)}"
        logger.warning(f"Vision API error: {e}")

    return result


def _fallback_image_interpretation(record: Record) -> dict:
    """
    Fallback: Return basic structure with note that no interpretation is available.
    """
    result = {
        "visible_object_type": None,
        "visible_materials": [],
        "visible_features": [],
        "uncertain_observations": ["No AI vision model available. Image interpretation not performed."],
        "caption": f"Image for {record.title}",
        "model": None,
        "confidence_note": "AI visual interpretation not available; requires human validation",
        "error": "No vision model configured (OpenAI API key missing)",
        "success": False
    }
    return result


def _fallback_image_interpretation_empty() -> dict:
    """Return empty fallback structure."""
    return {
        "visible_object_type": None,
        "visible_materials": [],
        "visible_features": [],
        "uncertain_observations": ["Image interpretation not available"],
        "caption": None,
        "model": None,
        "confidence_note": "AI visual interpretation not available; requires human validation",
        "error": "Vision model not configured",
        "success": False
    }


def visual_index_record_image(record: Record, top_k: int = 5) -> dict:
    """
    Classify a record image against cultural-heritage visual labels using OpenCLIP.

    This is zero-shot inference: no project-specific training or fine-tuning is
    performed. Results are proposed observations for review.
    """
    result = {
        "success": False,
        "model": f"openclip:{_CLIP_MODEL_NAME}:{_CLIP_PRETRAINED}",
        "method": "open_clip_zero_shot",
        "top_labels": [],
        "primary_label": None,
        "primary_claim_type": None,
        "primary_score": 0.0,
        "caption": None,
        "confidence_note": "Zero-shot visual indexing; requires human validation",
        "error": None,
    }
    if not (record.image_url or record.local_image_path):
        result["error"] = "No image available for visual indexing"
        return result

    try:
        import torch
        from PIL import Image
    except ImportError as exc:
        result["error"] = f"Visual indexing dependencies unavailable: {exc}"
        return result

    try:
        model, preprocess, tokenizer = _load_openclip()
        image = _load_record_image(record)
        if image is None:
            result["error"] = "Could not load image"
            return result

        device = "cuda" if torch.cuda.is_available() else "cpu"
        image_input = preprocess(image.convert("RGB")).unsqueeze(0).to(device)
        prompt_texts = []
        prompt_to_label = []
        for label_def in VISUAL_INDEX_LABELS:
            for prompt in label_def["prompts"]:
                prompt_texts.append(prompt)
                prompt_to_label.append(label_def)

        text_input = tokenizer(prompt_texts).to(device)
        with torch.no_grad():
            image_features = model.encode_image(image_input)
            text_features = model.encode_text(text_input)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)
            similarities = (100.0 * image_features @ text_features.T).softmax(dim=-1)[0]

        label_scores: Dict[str, dict] = {}
        for score_tensor, label_def in zip(similarities, prompt_to_label):
            score = float(score_tensor.detach().cpu().item())
            label = label_def["label"]
            existing = label_scores.get(label)
            if existing is None:
                label_scores[label] = {
                    "label": label,
                    "claim_value": label_def["claim_value"],
                    "claim_type": label_def["claim_type"],
                    "score": score,
                    "best_prompt_score": score,
                }
            else:
                existing["score"] += score
                existing["best_prompt_score"] = max(existing["best_prompt_score"], score)

        ranked = sorted(label_scores.values(), key=lambda item: item["score"], reverse=True)[:top_k]
        if not ranked:
            result["error"] = "No labels scored"
            return result

        primary = ranked[0]
        result.update({
            "success": True,
            "top_labels": ranked,
            "primary_label": primary["claim_value"],
            "primary_claim_type": primary["claim_type"],
            "primary_score": primary["score"],
            "caption": _visual_index_caption(record, ranked),
        })
        return result
    except Exception as exc:
        result["error"] = f"Visual indexing failed: {exc}"
        logger.warning("Visual indexing failed: %s", exc)
        return result


def compare_visual_index_with_text(visual_indexing: dict, record: Record) -> dict:
    """Compare zero-shot visual labels with text fields already present on a record."""
    result = {
        "overall_alignment": "uncertain",
        "alignment_score": 0.0,
        "supports": [],
        "conflicts": [],
        "unmentioned_visual_observations": [],
        "text_checked": {},
        "notes": "",
    }
    if not visual_indexing.get("success"):
        result["notes"] = "Visual indexing not available. Cannot compare image and text."
        return result

    text_fields = {
        "title": record.title,
        "object_name": record.metadata.get("object_name") or record.metadata.get("object_type"),
        "description": record.metadata.get("description"),
        "materials": record.metadata.get("materials") or record.metadata.get("material") or record.metadata.get("medium"),
    }
    combined_text = " ".join(normalize_field_value(value).lower() for value in text_fields.values())
    result["text_checked"] = {key: normalize_field_value(value) for key, value in text_fields.items() if normalize_field_value(value)}

    supports = []
    unmentioned = []
    conflicts = []
    for scored in visual_indexing.get("top_labels", [])[:5]:
        label = scored.get("label", "")
        terms = next((item["text_terms"] for item in VISUAL_INDEX_LABELS if item["label"] == label), [])
        matched_terms = [term for term in terms if term.lower() in combined_text]
        score = float(scored.get("score", 0.0))
        if matched_terms:
            supports.append({
                "visual_label": scored.get("claim_value") or label,
                "score": score,
                "matched_text_terms": matched_terms,
            })
        elif score >= 0.12:
            unmentioned.append({
                "visual_label": scored.get("claim_value") or label,
                "score": score,
            })

    primary = visual_indexing.get("primary_label")
    object_text = " ".join(
        normalize_field_value(value).lower()
        for value in [record.metadata.get("object_name"), record.metadata.get("object_type"), record.title]
    )
    if primary and object_text:
        primary_terms = next((item["text_terms"] for item in VISUAL_INDEX_LABELS if item["claim_value"] == primary), [])
        if primary_terms and not any(term.lower() in object_text for term in primary_terms):
            conflicts.append({
                "visual_label": primary,
                "text_object_statement": object_text,
                "note": "Top visual label is not reflected in title/object-type text.",
            })

    result["supports"] = supports
    result["conflicts"] = conflicts
    result["unmentioned_visual_observations"] = unmentioned

    score = 0.35
    if supports:
        score += 0.45
    if unmentioned:
        score += 0.1
    if conflicts:
        score -= 0.25
    result["alignment_score"] = max(0.0, min(1.0, score))
    if result["alignment_score"] >= 0.7:
        result["overall_alignment"] = "supports_text"
    elif conflicts and not supports:
        result["overall_alignment"] = "possible_conflict"
    elif unmentioned:
        result["overall_alignment"] = "adds_visual_detail"
    else:
        result["overall_alignment"] = "uncertain"
    return result


def index_record_visual_evidence(record: Record) -> dict:
    """Run visual indexing and image/text alignment, storing both on the record."""
    visual_indexing = visual_index_record_image(record)
    alignment = compare_visual_index_with_text(visual_indexing, record)
    if isinstance(record.raw, dict):
        record.raw["visual_indexing"] = visual_indexing
        record.raw["image_text_alignment"] = alignment
    return {"visual_indexing": visual_indexing, "image_text_alignment": alignment}


@lru_cache(maxsize=1)
def _load_openclip():
    import open_clip
    import torch

    model, _, preprocess = open_clip.create_model_and_transforms(
        _CLIP_MODEL_NAME,
        pretrained=_CLIP_PRETRAINED,
    )
    tokenizer = open_clip.get_tokenizer(_CLIP_MODEL_NAME)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    model.eval()
    return model, preprocess, tokenizer


def _load_record_image(record: Record):
    from PIL import Image

    if record.local_image_path:
        return Image.open(record.local_image_path)
    image_url = record.image_url or ""
    if image_url.startswith("data:image/"):
        _, encoded = image_url.split(",", 1)
        return Image.open(BytesIO(base64.b64decode(encoded)))
    if image_url:
        import requests

        response = requests.get(image_url, timeout=20)
        response.raise_for_status()
        return Image.open(BytesIO(response.content))
    return None


def _visual_index_caption(record: Record, ranked: List[dict]) -> str:
    labels = ", ".join(f"{item['claim_value']} ({item['score']:.2f})" for item in ranked[:3])
    return f"Zero-shot visual indexing for '{record.title}' ranked: {labels}."


def compare_image_text_consistency(
    image_interpretation: dict,
    textual_claims: Dict[str, str]
) -> dict:
    """
    Compare image-derived observations with textual claims.

    Args:
        image_interpretation: Output from interpret_record_image()
        textual_claims: dict of field -> value from record metadata
            e.g., {"object_name": "harpsichord", "materials": "wood and ivory"}

    Returns:
        dict: {
            "overall_consistency": "high" | "medium" | "low" | "uncertain",
            "consistency_score": float 0-1,
            "matches": [...],
            "contradictions": [...],
            "missing_from_image": [...],
            "notes": "...",
            "confidence": "..."
        }
    """
    result = {
        "overall_consistency": "uncertain",
        "consistency_score": 0.5,
        "matches": [],
        "contradictions": [],
        "missing_from_image": [],
        "notes": "",
        "confidence": "Low confidence comparison due to limited AI vision data"
    }

    if not image_interpretation.get("success"):
        result["notes"] = "Image interpretation not available. Cannot compare."
        return result

    try:
        visible_type = (image_interpretation.get("visible_object_type") or "").lower()
        visible_materials = [m.lower() for m in (image_interpretation.get("visible_materials") or [])]
        visible_features = [f.lower() for f in (image_interpretation.get("visible_features") or [])]

        # Compare object type
        text_object_type = str(textual_claims.get("object_name", "")).lower()
        if visible_type and text_object_type:
            if visible_type in text_object_type or text_object_type in visible_type:
                result["matches"].append(f"Object type: '{visible_type}' matches textual '{text_object_type}'")
            else:
                result["contradictions"].append(f"Object type: visible '{visible_type}' vs text '{text_object_type}'")
        elif visible_type:
            result["matches"].append(f"Object type visible: {visible_type}")
        elif text_object_type:
            result["missing_from_image"].append(f"Object type in text but not visible: {text_object_type}")

        # Compare materials
        text_materials = str(textual_claims.get("materials", "")).lower()
        if text_materials and visible_materials:
            for mat in visible_materials:
                if mat in text_materials:
                    result["matches"].append(f"Material '{mat}' appears in both image and text")
                else:
                    result["missing_from_image"].append(f"Material '{mat}' visible but not mentioned in text")
            # Check for text-only materials
            for word in text_materials.split():
                if word not in visible_materials and len(word) > 3:
                    result["missing_from_image"].append(f"Text mentions material '{word}' but not visible in image")
        elif visible_materials:
            result["matches"].append(f"Materials visible: {', '.join(visible_materials)}")
        elif text_materials:
            result["missing_from_image"].append(f"Text claims materials but no image available")

        # Calculate consistency score
        score = 0.5
        if result["matches"]:
            score += 0.3
        if result["contradictions"]:
            score -= 0.2
        if result["missing_from_image"]:
            score -= 0.1

        result["consistency_score"] = max(0, min(1, score))

        if result["consistency_score"] > 0.7:
            result["overall_consistency"] = "high"
        elif result["consistency_score"] > 0.4:
            result["overall_consistency"] = "medium"
        else:
            result["overall_consistency"] = "low"

    except Exception as e:
        logger.warning(f"Consistency comparison failed: {e}")
        result["notes"] = f"Comparison error: {e}"

    return result
