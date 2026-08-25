import re
import unicodedata


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(re.sub(r"[^a-zA-Z0-9]+", " ", ascii_value).lower().split())


def slugify(value: str) -> str:
    return normalize_text(value).replace(" ", "-")
