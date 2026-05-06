"""Embeddings module for text and image processing."""

import logging
from io import BytesIO
from typing import Dict, Optional

import numpy as np
import requests
from PIL import Image

from src.settings import CLIP_MODEL, CLIP_PRETRAINED, DEVICE

logger = logging.getLogger(__name__)

_clip_model = None
_clip_tokenizer = None
_clip_preprocess = None
_open_clip = None
_torch = None
_clip_import_attempted = False


def _ensure_clip_imports():
    global _open_clip, _torch, _clip_import_attempted

    if _open_clip is not None and _torch is not None:
        return True
    if _clip_import_attempted:
        return False

    _clip_import_attempted = True
    try:
        import open_clip  # type: ignore
        import torch  # type: ignore

        _open_clip = open_clip
        _torch = torch
        return True
    except Exception as exc:
        logger.warning("CLIP import failed: %s", exc)
        return False


def _load_clip():
    """Load CLIP model lazily."""
    global _clip_model, _clip_tokenizer, _clip_preprocess

    if _clip_model is not None and _clip_tokenizer is not None and _clip_preprocess is not None:
        return _clip_model, _clip_tokenizer, _clip_preprocess

    if not _ensure_clip_imports():
        return None, None, None

    try:
        model, _, preprocess = _open_clip.create_model_and_transforms(
            CLIP_MODEL,
            pretrained=CLIP_PRETRAINED,
            device=DEVICE,
        )
        tokenizer = _open_clip.get_tokenizer(CLIP_MODEL)

        _clip_model = model
        _clip_tokenizer = tokenizer
        _clip_preprocess = preprocess

        logger.info(f"Loaded CLIP model: {CLIP_MODEL}")
        return _clip_model, _clip_tokenizer, _clip_preprocess

    except Exception as e:
        logger.error(f"Failed to load CLIP: {e}")
        return None, None, None


def embed_text(text: str) -> Optional[np.ndarray]:
    """
    Generate embedding for text using CLIP.
    
    Args:
        text: Text to embed
    
    Returns:
        512-dim L2-normalized numpy array or None
    """
    if not text or not isinstance(text, str):
        return None

    try:
        model, tokenizer, _ = _load_clip()
        if model is None or tokenizer is None or _torch is None:
            return None

        tokens = tokenizer(text).to(DEVICE)

        with _torch.no_grad():
            text_features = model.encode_text(tokens)

        embedding = text_features / text_features.norm(p=2, dim=-1, keepdim=True)
        emb_np = embedding.cpu().numpy()[0]
        emb_np = emb_np / np.linalg.norm(emb_np)
        return emb_np

    except Exception as e:
        logger.debug(f"Error embedding text: {e}")
        return None


def embed_image(image_url: Optional[str]) -> Optional[np.ndarray]:
    """
    Generate embedding for image using CLIP.
    """
    if not image_url:
        return None

    try:
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()
        image = Image.open(BytesIO(response.content))

        if image.mode == "RGBA":
            image = image.convert("RGB")

        model, _, preprocess = _load_clip()
        if model is None or preprocess is None or _torch is None:
            return None

        image_tensor = preprocess(image).unsqueeze(0).to(DEVICE)

        with _torch.no_grad():
            image_features = model.encode_image(image_tensor)

        embedding = image_features / image_features.norm(p=2, dim=-1, keepdim=True)
        emb_np = embedding.cpu().numpy()[0]
        emb_np = emb_np / np.linalg.norm(emb_np)
        return emb_np

    except Exception as e:
        logger.debug(f"Error embedding image {image_url}: {e}")
        return None


def batch_embed_texts(texts: list) -> Dict[str, Optional[np.ndarray]]:
    """
    Embed multiple texts efficiently.
    
    Args:
        texts: List of text strings
    
    Returns:
        Dict mapping text -> embedding (or None if failed)
    """
    embeddings = {}
    for text in texts:
        embeddings[text] = embed_text(text)
    return embeddings


def compute_cosine_similarity(emb1: Optional[np.ndarray], 
                             emb2: Optional[np.ndarray]) -> Optional[float]:
    """
    Compute cosine similarity between two embeddings.
    
    Args:
        emb1: First embedding or None
        emb2: Second embedding or None
    
    Returns:
        Cosine similarity in [-1, 1] or None if either is None
    """
    if emb1 is None or emb2 is None:
        return None
    
    # Ensure L2 normalized
    emb1 = emb1 / np.linalg.norm(emb1)
    emb2 = emb2 / np.linalg.norm(emb2)
    
    return float(np.dot(emb1, emb2))
