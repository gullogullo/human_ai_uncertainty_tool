"""Configuration and constants for the source-record and uncertainty exploration tool."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = PROJECT_ROOT / "cache"

DATA_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

# APIs
EUROPEANA_API = "https://api.europeana.eu/api/v2/search.json"
THE_MET_API = "https://collectionapi.metmuseum.org/public/collection/v1"
RIJKSMUSEUM_SEARCH_API = "https://data.rijksmuseum.nl/search/collection"
VICTORIA_AND_ALBERT_API = "https://api.vam.ac.uk/v2"

EUROPEANA_KEY = os.getenv("EUROPEANA_KEY", None)

# Source registry
SOURCE_REGISTRY = {
    "europeana": {
        "type": "api_aggregator",
        "label": "Europeana",
        "enabled": True
    },
    "the_met": {
        "type": "api_museum",
        "label": "The Met",
        "enabled": True
    },
    "victoria_and_albert": {
        "type": "api_museum",
        "label": "Victoria and Albert Museum",
        "enabled": True
    },
    "boalch": {
        "type": "authority_database",
        "label": "Boalch–Mould Online",
        "enabled": True,
        "access": "non_api_scraping_or_manual_dataset"
    },
    "philharmonie": {
        "type": "museum_collection",
        "label": "Philharmonie de Paris Museum Collections",
        "enabled": True,
        "access": "non_api_scraping_or_manual_dataset"
    },
    "carmentis": {
        "type": "museum_collection",
        "label": "Carmentis",
        "enabled": True,
        "access": "user_provided_url_or_manual_dataset"
    },
    "manual": {
        "type": "user_added_evidence",
        "label": "Manual / External Record",
        "enabled": True
    }
}

API_SOURCES = ["europeana", "the_met", "victoria_and_albert"]
NON_API_SOURCES = ["boalch", "philharmonie", "carmentis"]
SEMANTIC_SOURCES = []

# Embedding & vision
CLIP_MODEL = "ViT-B-32"
CLIP_PRETRAINED = "openai"
EMBEDDING_DIM = 512
DEVICE = "cpu"

# UI Settings
DEBUG_UI = False
SHOW_DIRECT_EVIDENCE_TABLES = False
ALLOW_USER_PROVIDED_NON_API_URL_FETCH = True

# Thresholds
THRESHOLDS = {
    "coverage_low": 0.5,
    "text_sim_low": 0.7,
    "image_text_sim_low": 0.6,
}

# Streamlit page config
STREAMLIT_PAGE_CONFIG = {
    "page_title": "DIMA — Data Inspection for Multimedia Artefacts",
    "page_icon": "🕸️",
    "layout": "wide",
    "initial_sidebar_state": "expanded",
}

LOG_LEVEL = "INFO"
