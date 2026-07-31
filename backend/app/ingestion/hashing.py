import hashlib
import re


def normalize_content(text: str) -> str:
    """Collapse whitespace so trivial reformatting doesn't change the hash."""
    return re.sub(r"\s+", " ", text).strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_content(text).encode("utf-8")).hexdigest()
