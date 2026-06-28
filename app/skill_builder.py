from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.media import format_clock, slugify
from app.ocr_filter import filter_ocr_lines
from app.text_analysis import (
    best_on_screen_line,
    build_description,
    build_overview_intro,
    clean_title,
    extract_key_terms,
)
from app.transcribe import TranscriptResult
from app.video_analysis import VideoAnalysisResult


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


def _build_overview(
    transcript: TranscriptResult,
    visual: VideoAnalysisResult | None,
    key_terms: list[str],
) -> str:
    intro = build_overview_intro(transcript, key_terms)

    if visual and visual.frames_analyzed:
        intro += f" Visual notes were captured from {visual.frames_analyzed} sampled frames."

    return intro


def _merge_timeline(
    transcript: TranscriptResult,
    visual: VideoAnalysisResult | None,
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
            entry.on_screen.extend(filter_ocr_lines(frame.ocr_text))
            if frame.description:
                entry.visual_notes.append(frame.description)

    for entry in entries.values():
        entry.on_screen = filter_ocr_lines(entry.on_screen)

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
            filtered = filter_ocr_lines(frame.ocr_text)
            if not filtered and not frame.description:
                continue
            lines.append(f"### {frame.source}")
            if filtered:
                lines.append("")
                lines.append("OCR:")
                for line in filtered:
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


def build_skill_bundle(
    *,
    source_name: str,
    transcript: TranscriptResult,
    visual: VideoAnalysisResult | None,
    skill_name: str | None = None,
) -> SkillBundle:
    base_name = Path(source_name).stem
    resolved_name = slugify(skill_name or base_name)
    key_terms = extract_key_terms(transcript, visual)
    entries = _merge_timeline(transcript, visual)
    overview = _build_overview(transcript, visual, key_terms)
    timeline_md = _render_timeline(entries)
    reference_md = _render_reference(
        source_name=source_name,
        transcript=transcript,
        visual=visual,
        entries=entries,
    )

    title = clean_title(base_name)
    description = build_description(title=title, key_terms=key_terms, has_visual=bool(visual and visual.frames))

    concept_lines = [f"- {term}" for term in key_terms] or ["- Review the timeline and transcript in `reference.md`."]

    procedure_lines: list[str] = []
    step_number = 1
    for entry in entries:
        if not entry.speech:
            continue
        summary = entry.speech[0]
        if len(summary) > 180:
            summary = summary[:177].rstrip() + "..."

        on_screen = best_on_screen_line(entry.on_screen, summary)
        visual_note = entry.visual_notes[0] if entry.visual_notes else None

        extras: list[str] = []
        if on_screen:
            extras.append(f"On-screen: {on_screen}")
        if visual_note:
            extras.append(f"Visual: {visual_note}")
        suffix = f" ({'; '.join(extras)})" if extras else ""
        procedure_lines.append(f"{step_number}. **{format_clock(entry.timestamp)}** — {summary}{suffix}")
        step_number += 1
        if step_number > 12:
            break

    if not procedure_lines:
        procedure_lines.append("1. Read the full transcript and timeline in `reference.md`.")

    trigger_terms = ", ".join(f"`{term}`" for term in key_terms[:5]) or "the material in `reference.md`"

    skill_md = f"""---
name: {resolved_name}
description: {description}
---

# {title}

## Overview
{overview}

## When to use this skill
- The user asks about {title.lower()} or related UI/UX design guidance from the source video.
- The user references concepts such as {trigger_terms}.
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
