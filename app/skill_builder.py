from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.media import format_clock, slugify
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
    "should",
    "start",
    "than",
    "that",
    "the",
    "their",
    "there",
    "these",
    "they",
    "this",
    "through",
    "use",
    "using",
    "very",
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


def _extract_heading_terms(visual: VideoAnalysisResult | None) -> list[str]:
    if not visual:
        return []

    headings: list[str] = []
    seen: set[str] = set()
    for frame in visual.frames:
        for line in frame.ocr_text:
            cleaned = line.strip()
            if len(cleaned) < 4:
                continue
            looks_like_heading = (
                "&" in cleaned
                or (cleaned[0].isupper() and sum(1 for char in cleaned if char.isupper()) >= 2)
                or cleaned.isupper()
            )
            if not looks_like_heading:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            headings.append(cleaned)
    return headings[:8]


@dataclass
class SkillBundle:
    skill_name: str
    skill_md: str
    reference_md: str
    timeline_md: str


@dataclass
class TimelineEntry:
    timestamp: float
    speech: list[str]
    on_screen: list[str]
    visual_notes: list[str]


def _tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text.lower())
    return [word for word in words if word not in STOPWORDS]


def _extract_key_terms(transcript: TranscriptResult, visual: VideoAnalysisResult | None) -> list[str]:
    counter: Counter[str] = Counter()

    for segment in transcript.segments:
        counter.update(_tokenize(segment.text))

    if visual:
        for frame in visual.frames:
            for line in frame.ocr_text:
                counter.update(_tokenize(line))

    ranked = [term for term, count in counter.most_common(20) if count >= 2 and len(term) >= 4]
    heading_terms = _extract_heading_terms(visual)
    merged: list[str] = []
    seen: set[str] = set()
    for term in heading_terms + ranked:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(term)
    return merged[:8]


def _build_overview(transcript: TranscriptResult, visual: VideoAnalysisResult | None) -> str:
    intro = " ".join(segment.text for segment in transcript.segments[:4]).strip()
    if len(intro) > 420:
        intro = intro[:417].rstrip() + "..."

    parts = [intro or "This skill captures knowledge extracted from a source video."]
    if visual and visual.frames_analyzed:
        parts.append(
            f"Visual analysis sampled {visual.frames_analyzed} frames, including scene changes "
            f"and on-screen text detected via OCR."
        )
        if visual.ollama_model:
            parts.append(f"Frame descriptions were generated with Ollama model `{visual.ollama_model}`.")
    return " ".join(parts)


def _merge_timeline(
    transcript: TranscriptResult,
    visual: VideoAnalysisResult | None,
    *,
    window_seconds: float = 18.0,
) -> list[TimelineEntry]:
    entries: dict[int, TimelineEntry] = {}

    for segment in transcript.segments:
        bucket = int(round(segment.start / 15.0) * 15)
        entry = entries.setdefault(bucket, TimelineEntry(timestamp=float(bucket), speech=[], on_screen=[], visual_notes=[]))
        entry.speech.append(segment.text)

    if visual:
        for frame in visual.frames:
            bucket = int(round(frame.timestamp / 15.0) * 15)
            entry = entries.setdefault(bucket, TimelineEntry(timestamp=float(bucket), speech=[], on_screen=[], visual_notes=[]))
            entry.on_screen.extend(frame.ocr_text)
            if frame.description:
                entry.visual_notes.append(frame.description)

    return [entries[key] for key in sorted(entries)]


def _render_timeline(entries: list[TimelineEntry]) -> str:
    lines = ["# Timeline", ""]
    for entry in entries:
        lines.append(f"## {format_clock(entry.timestamp)}")
        lines.append("")

        if entry.speech:
            lines.append("### Spoken content")
            for chunk in entry.speech:
                lines.append(f"- {chunk}")
            lines.append("")

        if entry.on_screen:
            lines.append("### On-screen text")
            for chunk in entry.on_screen:
                lines.append(f"- {chunk}")
            lines.append("")

        if entry.visual_notes:
            lines.append("### Visual context")
            for chunk in entry.visual_notes:
                lines.append(f"- {chunk}")
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def _render_reference(
    *,
    source_name: str,
    transcript: TranscriptResult,
    visual: VideoAnalysisResult | None,
    entries: list[TimelineEntry],
) -> str:
    lines = [
        "# Reference Notes",
        "",
        f"- Source file: `{source_name}`",
        f"- Duration: {format_clock(transcript.duration)}",
        f"- Detected language: {transcript.language}",
        "",
        "## Full transcript",
        "",
        transcript.text,
        "",
    ]

    if visual and visual.frames:
        lines.extend(["## Visual frame notes", ""])
        for frame in visual.frames:
            lines.append(f"### {frame.source}")
            if frame.ocr_text:
                lines.append("")
                lines.append("OCR:")
                for line in frame.ocr_text:
                    lines.append(f"- {line}")
            if frame.description:
                lines.append("")
                lines.append(f"Vision: {frame.description}")
            lines.append("")

    lines.extend(["## Merged timeline", ""])
    for entry in entries:
        if not (entry.speech or entry.on_screen or entry.visual_notes):
            continue
        lines.append(f"### {format_clock(entry.timestamp)}")
        if entry.speech:
            lines.append(f"- Speech: {' '.join(entry.speech)}")
        for line in entry.on_screen:
            lines.append(f"- On-screen: {line}")
        for note in entry.visual_notes:
            lines.append(f"- Visual: {note}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _build_description(source_name: str, key_terms: list[str], has_visual: bool) -> str:
    topic = Path(source_name).stem.replace("_", " ").replace("-", " ").strip() or "video content"
    term_hint = ", ".join(key_terms[:5]) if key_terms else topic
    visual_hint = " Includes on-screen text and visual context from frame analysis." if has_visual else ""
    return (
        f"Provides extracted knowledge from `{topic}` covering {term_hint}. "
        f"Use when the user asks about this topic, workflow, or material from the source video.{visual_hint}"
    )


def build_skill_bundle(
    *,
    source_name: str,
    transcript: TranscriptResult,
    visual: VideoAnalysisResult | None,
    skill_name: str | None = None,
) -> SkillBundle:
    base_name = Path(source_name).stem
    resolved_name = slugify(skill_name or base_name)
    key_terms = _extract_key_terms(transcript, visual)
    overview = _build_overview(transcript, visual)
    entries = _merge_timeline(transcript, visual)
    timeline_md = _render_timeline(entries)
    reference_md = _render_reference(
        source_name=source_name,
        transcript=transcript,
        visual=visual,
        entries=entries,
    )

    title = base_name.replace("_", " ").replace("-", " ").strip() or "Extracted Video Knowledge"
    description = _build_description(source_name, key_terms, bool(visual and visual.frames))

    concept_lines = [f"- {term}" for term in key_terms] or ["- Review the timeline and transcript in `reference.md`."]

    procedure_lines: list[str] = []
    step_number = 1
    for entry in entries:
        if not entry.speech:
            continue
        summary = entry.speech[0]
        if len(summary) > 180:
            summary = summary[:177].rstrip() + "..."
        extras: list[str] = []
        if entry.on_screen:
            extras.append(f"On-screen: {entry.on_screen[0]}")
        if entry.visual_notes:
            extras.append(f"Visual: {entry.visual_notes[0]}")
        suffix = f" ({'; '.join(extras)})" if extras else ""
        procedure_lines.append(f"{step_number}. **{format_clock(entry.timestamp)}** — {summary}{suffix}")
        step_number += 1
        if step_number > 12:
            break

    if not procedure_lines:
        procedure_lines.append("1. Read the full transcript and timeline in `reference.md`.")

    skill_md = f"""---
name: {resolved_name}
description: {description}
---

# {title}

## Overview
{overview}

## When to use this skill
- The user asks about `{title}` or related workflows captured in the source video.
- The user references concepts such as {", ".join(f"`{term}`" for term in key_terms[:5]) or "the material in `reference.md`"}.
- You need step-by-step guidance that combines spoken explanation with on-screen context.

## Key concepts
{chr(10).join(concept_lines)}

## Procedure
{chr(10).join(procedure_lines)}

## Visual and on-screen knowledge
- Detailed OCR, frame notes, and a timestamped merge live in `reference.md`.
- Prefer on-screen text for exact names, commands, URLs, and UI labels.
- Prefer spoken transcript segments for intent, reasoning, and sequence.

## Agent instructions
1. Start with the procedure above for the user's goal.
2. Pull exact strings (commands, settings, labels) from on-screen notes in `reference.md`.
3. Use visual notes to disambiguate UI steps that are not fully spoken aloud.
4. If the user needs deeper context, quote or summarize the relevant timeline section.

## Source
- File: `{source_name}`
- Duration: {format_clock(transcript.duration)}
- Language: {transcript.language}
"""

    return SkillBundle(
        skill_name=resolved_name,
        skill_md=skill_md.strip() + "\n",
        reference_md=reference_md,
        timeline_md=timeline_md,
    )