from __future__ import annotations

import re
import unicodedata


def normalize_company_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_short_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = normalize_company_name(value)
    return normalized or None
