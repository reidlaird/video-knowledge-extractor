from __future__ import annotations

import re
from collections import Counter

from app.ocr_filter import filter_ocr_lines, is_demo_content_ocr
from app.transcribe import TranscriptResult
from app.video_analysis import VideoAnalysisResult

STOPWORDS = {
    "about",
    "after",
    "also",
    "and",
    "any",
    "are",
    "back",
    "because",
    "before",
    "being",
    "between",
    "but",
    "can",
    "could",
    "first",
    "for",
    "from",
    "get",
    "good",
    "have",
    "how",
    "into",
    "just",
    "know",
    "like",
    "look",
    "make",
    "minute",
    "more",
    "need",
    "not",
    "now",
    "one",
    "other",
    "our",
    "out",
    "really",
    "right",
    "screen",
    "should",
    "some",
    "start",
    "super",
    "take",
    "than",
    "that",
    "the",
    "their",
    "there",
    "these",
    "they",
    "thing",
    "things",
    "this",
    "through",
    "today",
    "use",
    "using",
    "very",
    "video",
    "want",
    "was",
    "way",
    "what",
    "when",
    "where",
    "which",
    "will",
    "with",
    "would",
    "you",
    "your",
}

DOMAIN_TERMS = {
    "accessibility",
    "affordance",
    "affordances",
    "animation",
    "announcement bar",
    "blur",
    "button",
    "button states",
    "buttons",
    "color",
    "color ramp",
    "contrast",
    "dark mode",
    "dashboard",
    "dashboards",
    "design",
    "feedback",
    "figma",
    "focus state",
    "four point grid",
    "ghost button",
    "gradient",
    "grid",
    "hierarchy",
    "hover",
    "hover state",
    "icon",
    "icons",
    "input",
    "interaction",
    "interactions",
    "landing page",
    "landing pages",
    "layout",
    "letter spacing",
    "line height",
    "micro interaction",
    "micro interactions",
    "overlay",
    "overlays",
    "progressive blur",
    "responsiveness",
    "semantic",
    "semantic colors",
    "shadow",
    "shadows",
    "signifier",
    "signifiers",
    "spacing",
    "typography",
    "ui",
    "ux",
    "visual hierarchy",
    "whitespace",
    "white space",
}

MAX_OCR_CONCEPTS = 2
MIN_ON_SCREEN_SCORE = 4


GENERIC_TERMS = {
    "button",
    "buttons",
    "color",
    "design",
    "icon",
    "icons",
    "look",
    "make",
    "need",
    "screen",
    "size",
    "text",
    "ui",
    "users",
    "ux",
    "video",
}


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text.lower())
    return [word for word in words if word not in STOPWORDS]


def extract_phrases(text: str, *, sizes: tuple[int, ...] = (2, 3)) -> list[str]:
    words = [word for word in re.findall(r"[a-zA-Z][a-zA-Z0-9-]*", text.lower()) if word not in STOPWORDS]
    phrases: list[str] = []

    for size in sizes:
        for index in range(len(words) - size + 1):
            chunk = words[index : index + size]
            phrase = " ".join(chunk)
            if len(phrase) >= 5:
                phrases.append(phrase)

    return phrases


def extract_domain_phrases_from_text(text: str) -> list[tuple[str, int]]:
    lowered = text.lower()
    found: list[tuple[str, int]] = []
    covered: set[str] = set()

    for term in sorted(DOMAIN_TERMS, key=len, reverse=True):
        count = lowered.count(term)
        if count == 0:
            continue
        if any(term in existing or existing in term for existing in covered):
            continue
        found.append((term, count))
        covered.add(term)

    return found


def _normalize_heading(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def extract_heading_terms(visual: VideoAnalysisResult | None, *, transcript_text: str) -> list[str]:
    if not visual:
        return []

    headings: list[str] = []
    seen: set[str] = set()
    transcript_lower = transcript_text.lower()

    for frame in visual.frames:
        for line in filter_ocr_lines(frame.ocr_text):
            cleaned = _normalize_heading(line)
            looks_like_heading = "&" in cleaned or (
                cleaned[0].isupper() and sum(1 for char in cleaned if char.isupper()) >= 2 and len(cleaned) <= 60
            )
            if not looks_like_heading:
                continue

            key = cleaned.lower()
            supported = key in transcript_lower or "&" in cleaned or _heading_overlaps_speech(cleaned, transcript_text)
            if not supported:
                continue

            if key in seen:
                continue
            seen.add(key)
            for part in _split_compound_heading(cleaned):
                part_key = part.lower()
                if part_key in seen:
                    continue
                seen.add(part_key)
                headings.append(part)

    return headings[:6]


def _split_compound_heading(heading: str) -> list[str]:
    if "&" not in heading:
        return [heading]

    parts = [re.sub(r"\s+", " ", part).strip() for part in heading.split("&") if part.strip()]
    return parts if len(parts) >= 2 else [heading]


def _heading_overlaps_speech(heading: str, transcript_text: str) -> bool:
    heading_tokens = set(tokenize(heading))
    if not heading_tokens:
        return False
    overlap = len(heading_tokens & set(tokenize(transcript_text)))
    return overlap >= max(1, len(heading_tokens) // 2)


JUNK_PHRASES = {
    "all of",
    "kind of",
    "lot of",
    "one of",
    "part of",
    "this is",
}


CONCEPT_ALIASES = {
    "visual hierarchy": "hierarchy",
    "whitespace": "white space",
}

SPEECH_CONCEPT_ALIASES: dict[str, tuple[str, ...]] = {
    "affordances": ("afford", "affords", "affordance"),
}

TIER1_PREFERRED_ORDER = [
    "hierarchy",
    "typography",
    "white space",
    "signifiers",
    "affordances",
    "dark mode",
    "shadows",
    "micro interactions",
    "semantic colors",
    "overlays",
]

TIER1_CONCEPTS = {
    "affordances",
    "dark mode",
    "hierarchy",
    "micro interactions",
    "overlays",
    "semantic colors",
    "shadows",
    "signifiers",
    "typography",
    "visual hierarchy",
    "white space",
}

PRIORITY_CONCEPTS = TIER1_CONCEPTS | {
    "announcement bar",
    "color ramp",
    "contrast",
    "feedback",
    "focus state",
    "ghost button",
    "grid",
    "hover state",
    "progressive blur",
    "responsiveness",
}


def _canonical_concept_key(term: str) -> str:
    lowered = term.lower().strip()
    return CONCEPT_ALIASES.get(lowered, lowered)


def _normalize_concept_label(term: str) -> str:
    key = _canonical_concept_key(term)
    if key in TIER1_CONCEPTS or key in PRIORITY_CONCEPTS:
        return key
    return term


def _dedupe_concepts(terms: list[str]) -> list[str]:
    seen_keys: set[str] = set()
    deduped: list[str] = []
    for term in terms:
        label = _normalize_concept_label(term)
        key = _canonical_concept_key(label)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(label)
    return deduped


def _detect_alias_concepts(text: str) -> list[tuple[str, int]]:
    lowered = text.lower()
    found: list[tuple[str, int]] = []
    for concept, aliases in SPEECH_CONCEPT_ALIASES.items():
        count = sum(len(re.findall(rf"\b{re.escape(alias)}\b", lowered)) for alias in aliases)
        if count:
            found.append((concept, count))
    return found


def _tier1_sort_key(term: str, score: int) -> tuple[int, int, str]:
    key = _canonical_concept_key(term)
    try:
        preferred = TIER1_PREFERRED_ORDER.index(key)
    except ValueError:
        preferred = len(TIER1_PREFERRED_ORDER)
    return (preferred, -score, term.lower())


def _is_priority_concept(term: str) -> bool:
    return term.lower() in PRIORITY_CONCEPTS


def _is_junk_phrase(term: str) -> bool:
    lowered = term.lower().strip()
    if lowered in JUNK_PHRASES:
        return True
    words = lowered.split()
    if len(words) >= 2 and words[0] in STOPWORDS:
        return True
    return False


def _is_generic_concept(term: str) -> bool:
    lowered = term.lower().strip()
    return lowered in GENERIC_TERMS or len(lowered) <= 3


def _score_speech_term(term: str, *, count: int, transcript_text: str) -> int:
    lowered = term.lower()
    if _is_generic_concept(term):
        return 0

    score = count * 3
    if lowered in DOMAIN_TERMS:
        score += 12
    if " " in term:
        score += 4
    if lowered in transcript_text:
        score += 3
    if len(term) >= 8:
        score += 1
    return score


def _collect_speech_candidates(transcript: TranscriptResult) -> list[tuple[int, str]]:
    transcript_text = transcript.text.lower()
    word_counter: Counter[str] = Counter()
    phrase_counter: Counter[str] = Counter()

    for segment in transcript.segments:
        word_counter.update(tokenize(segment.text))
        phrase_counter.update(extract_phrases(segment.text))

    best_scores: dict[str, tuple[int, str]] = {}

    def consider(term: str, score: int) -> None:
        if score <= 0 or _is_junk_phrase(term) or _is_generic_concept(term):
            return
        key = term.lower()
        existing = best_scores.get(key)
        if existing is None or score > existing[0]:
            best_scores[key] = (score, term)

    for phrase, count in extract_domain_phrases_from_text(transcript.text):
        consider(phrase, _score_speech_term(phrase, count=count, transcript_text=transcript_text))

    for phrase, count in _detect_alias_concepts(transcript.text):
        consider(phrase, _score_speech_term(phrase, count=count, transcript_text=transcript_text))

    for phrase, count in phrase_counter.most_common(25):
        if count >= 2 or phrase in DOMAIN_TERMS:
            consider(phrase, _score_speech_term(phrase, count=count, transcript_text=transcript_text))

    for word, count in word_counter.most_common(30):
        if (count >= 3 or word in DOMAIN_TERMS) and len(word) >= 5 and not _is_generic_concept(word):
            consider(word, _score_speech_term(word, count=count, transcript_text=transcript_text))

    return list(best_scores.values())


def extract_key_terms(transcript: TranscriptResult, visual: VideoAnalysisResult | None) -> list[str]:
    transcript_text = transcript.text.lower()
    candidates = _collect_speech_candidates(transcript)
    candidates.sort(key=lambda item: (-item[0], item[1].lower()))

    ocr_added = 0
    for heading in extract_heading_terms(visual, transcript_text=transcript.text):
        if ocr_added >= MAX_OCR_CONCEPTS:
            break
        score = 20 if "&" in heading else 16
        candidates.append((score, heading))
        ocr_added += 1

    candidates.sort(key=lambda item: (-item[0], item[1].lower()))

    priority_scored: list[tuple[int, str]] = []
    secondary: list[str] = []
    seen: set[str] = set()

    for score, term in candidates:
        if is_demo_content_ocr(term) or _is_generic_concept(term):
            continue
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        if _is_priority_concept(term):
            priority_scored.append((score, term))
        else:
            secondary.append(term)

    tier1_scored = [
        (score, term)
        for score, term in priority_scored
        if _canonical_concept_key(term) in TIER1_CONCEPTS or term.lower() in TIER1_CONCEPTS
    ]
    tier1 = _dedupe_concepts(
        [term for score, term in sorted(tier1_scored, key=lambda item: _tier1_sort_key(item[1], item[0]))]
    )
    other_priority = _dedupe_concepts(
        [
            term
            for score, term in sorted(priority_scored, key=lambda item: (-item[0], item[1].lower()))
            if _canonical_concept_key(term) not in TIER1_CONCEPTS and term.lower() not in TIER1_CONCEPTS
        ]
    )

    merged = _dedupe_concepts(tier1 + other_priority + secondary)[:8]

    return merged


def best_on_screen_line(lines: list[str], speech: str) -> str | None:
    filtered = [line for line in filter_ocr_lines(lines) if not is_demo_content_ocr(line)]
    if not filtered:
        return None

    speech_tokens = set(tokenize(speech))
    best_line: str | None = None
    best_score = -1

    for line in filtered:
        line_tokens = set(tokenize(line))
        overlap = len(line_tokens & speech_tokens)
        score = overlap * 3

        if "&" in line:
            score += 5
        if overlap >= 2:
            score += 3
        if len(line) <= 55:
            score += 1
        if len(line) > 80:
            score -= 4
        if line.count(":") >= 3:
            score -= 3
        if re.search(r"^[A-Z][a-z]+(?:,\s*[A-Z]{2})+$", line):
            score -= 8
        if "&" not in line and overlap < 2:
            score -= 6
        if overlap == 0 and "&" not in line:
            score -= 5

        if score > best_score:
            best_score = score
            best_line = line

    if best_line is None or best_score < MIN_ON_SCREEN_SCORE:
        return None

    return best_line


def clean_title(raw: str) -> str:
    title = raw.replace("_", " ").replace("-", " ").strip()
    title = title.replace("⧸", "/").replace("  ", " ")
    return title or "Extracted Video Knowledge"


def build_description(*, title: str, key_terms: list[str], has_visual: bool) -> str:
    topic = clean_title(title)
    concept_hint = ", ".join(key_terms[:6]) if key_terms else "the concepts covered in the source video"
    trigger_hint = ", ".join(key_terms[:4]) if key_terms else topic.lower()

    description = (
        f"Explains {topic} including {concept_hint}. "
        f"Use when the user asks about {trigger_hint}, UI/UX design patterns, or guidance from this tutorial."
    )
    if has_visual:
        description += " Includes filtered on-screen text and visual notes from frame analysis."

    if len(description) > 900:
        description = description[:897].rstrip() + "..."

    return description


def build_overview_intro(transcript: TranscriptResult, key_terms: list[str]) -> str:
    intro_parts = [segment.text.strip() for segment in transcript.segments[:2] if segment.text.strip()]
    intro = " ".join(intro_parts)
    if len(intro) > 260:
        intro = intro[:257].rstrip() + "..."

    if not intro:
        intro = "This skill captures knowledge extracted from a source video."

    if key_terms:
        intro += f" Core topics include {', '.join(key_terms[:6])}."

    return intro
