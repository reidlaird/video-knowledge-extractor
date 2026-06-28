from __future__ import annotations

import re

GENERIC_UI_CHROME = {
    "clickable",
    "integrations",
    "message",
    "mobbin",
    "not clickable",
    "post a job opening",
    "post ajob opening",
    "projects",
    "rating",
    "references",
    "reports",
    "schedule an interview",
    "search for candidates",
    "send offer",
    "settings",
}

DEMO_NAV_LABELS = {
    "dessert",
    "drinks",
    "food",
    "position",
    "the drinks menu",
    "the food menu",
}

DEMO_CONTENT_WORDS = {
    "alfredo",
    "bolognese",
    "bowl",
    "burrito",
    "carbonara",
    "chipotle",
    "daiquiri",
    "gnocchi",
    "lasagna",
    "linguine",
    "margarita",
    "negroni",
    "old fashioned",
    "penne",
    "risotto",
    "shrimp",
    "tagliatelle",
}

NOISE_PATTERNS = (
    re.compile(r"@"),
    re.compile(r"^\d+\s*\|?\s*$"),
    re.compile(r"^#\s*\S+"),
    re.compile(r"^\W+$"),
    re.compile(r"^[a-z]{1,2}$"),
)

DEMO_PATTERNS = (
    re.compile(r"\$\s?\d"),
    re.compile(r"\bs\d+\.\d+\b", re.I),
    re.compile(r"\b\d{1,2}[:.]\d{2}\s?(am|pm)\b", re.I),
    re.compile(r"\b(deliver to|pickup from|total cost)\b", re.I),
    re.compile(r"\bhow can .? help you today\b", re.I),
    re.compile(r"\bproduct designer based\b", re.I),
    re.compile(r"\b(rating|projects)\s+\d", re.I),
    re.compile(r"\b(document ai|time & weather|download on ios)\b", re.I),
    re.compile(r"\b(los angeles|california|trusted by hundreds)\b", re.I),
    re.compile(r"^[A-Z][a-z]+(?:,\s*[A-Z]{2})+$"),
    re.compile(r"\b\d{2}\s+(thu|fri|mon|tue|wed|sat|sun)\b", re.I),
)


def is_demo_content_ocr(line: str) -> bool:
    text = re.sub(r"\s+", " ", line).strip()
    lowered = text.lower()

    if lowered in DEMO_NAV_LABELS:
        return True

    if lowered.startswith("the ") and lowered.endswith(" menu"):
        return True

    if any(word in lowered for word in DEMO_CONTENT_WORDS):
        return True

    if any(pattern.search(text) for pattern in DEMO_PATTERNS):
        return True

    title_case_words = re.findall(r"\b[A-Z][a-z]+\b", text)
    if len(title_case_words) >= 5 and "&" not in text:
        return True

    if text.count(",") >= 3 and len(text) > 45:
        return True

    if text.count(":") >= 4:
        return True

    return False


def is_noise_ocr_line(line: str) -> bool:
    text = re.sub(r"\s+", " ", line).strip()
    if len(text) < 3:
        return True

    lowered = text.lower()
    if lowered in GENERIC_UI_CHROME:
        return True

    if any(pattern.search(text) for pattern in NOISE_PATTERNS):
        return True

    if is_demo_content_ocr(text):
        return True

    alpha = sum(1 for char in text if char.isalpha())
    if alpha < 3:
        return True

    if len(text) > 120 and ":" not in text and "&" not in text:
        return True

    words = re.findall(r"[a-zA-Z]+", lowered)
    if len(words) == 1 and len(words[0]) <= 4 and words[0] not in {"grid", "color", "size"}:
        return True

    return False


def filter_ocr_lines(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for line in lines:
        text = re.sub(r"\s+", " ", line).strip()
        if is_noise_ocr_line(text):
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned
