"""String normalization and similarity utilities."""

import difflib
import re
import unicodedata


def normalize_text(text: str) -> str:
    """Normalize text for fuzzy matching."""
    if not text:
        return ""
    text = text.lower()
    # Remove common suffixes in parentheses/brackets
    text = re.sub(
        r"\s*[\(\[].*?(radio|edit|remaster|live|version|remix|acoustic|"
        r"feat\.?|ft\.?|bonus|extended|single|album|original|official|"
        r"video|audio|hd|hq|\d{4}).*?[\)\]]",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Remove " - Remastered YYYY" style suffixes
    text = re.sub(
        r"\s*[-–—]\s*(remaster|live|acoustic|remix|ao vivo|remasterizado).*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Normalize unicode (é -> e)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    # Keep only alphanumeric and spaces
    text = re.sub(r"[^\w\s]", " ", text)
    # Collapse whitespace
    text = " ".join(text.split())
    return text


def similarity(s1: str, s2: str) -> float:
    """Calculate similarity ratio between two strings."""
    return difflib.SequenceMatcher(None, s1, s2).ratio()
