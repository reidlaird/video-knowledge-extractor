from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.jobs import ProgressCallback
from app.media import is_video
from app.output import resolve_output_dir, save_analyze_result
from app.skill_builder import SkillBundle, build_skill_bundle
from app.transcribe import TranscriptResult, segments_to_srt, transcribe_file
from app.video_analysis import VideoAnalysisResult, analyze_video


@dataclass
class AnalyzeResult:
    filename: str
    transcript: TranscriptResult
    visual: VideoAnalysisResult | None
    skill: SkillBundle


def analyze_media(
    source: Path,
    work_dir: Path,
    *,
    model_name: str = "base",
    language: str | None = None,
    interval_seconds: float = 30.0,
    scene_threshold: float = 0.35,
    max_frames: int = 40,
    use_ocr: bool = True,
    use_ollama_vision: bool = False,
    ollama_base_url: str = "http://127.0.0.1:11434",
    ollama_model: str = "llava",
    skill_name: str | None = None,
    output_dir: Path | None = None,
    on_progress: ProgressCallback | None = None,
) -> tuple[AnalyzeResult, Path, list[str]]:
    def emit(stage: str, percent: int, message: str) -> None:
        if on_progress:
            on_progress(stage, percent, message)

    emit("transcribing", 8, "Transcribing audio with Whisper…")
    transcript = transcribe_file(source, model_name=model_name, language=language)
    emit("transcribing", 38, "Transcription complete.")

    visual: VideoAnalysisResult | None = None
    if is_video(source):
        emit("detecting_scenes", 42, "Detecting scene changes and sampling frames…")
        visual = analyze_video(
            source,
            work_dir,
            interval_seconds=interval_seconds,
            scene_threshold=scene_threshold,
            max_frames=max_frames,
            use_ocr=use_ocr,
            use_ollama_vision=use_ollama_vision,
            ollama_base_url=ollama_base_url,
            ollama_model=ollama_model,
            on_progress=on_progress,
        )
        emit("analyzing_frames", 82, f"Analyzed {visual.frames_analyzed} frames.")
    else:
        emit("analyzing_frames", 82, "Audio-only file — skipping visual analysis.")

    emit("building_skill", 88, "Building skill documents…")
    skill = build_skill_bundle(
        source_name=source.name,
        transcript=transcript,
        visual=visual,
        skill_name=skill_name,
    )

    result = AnalyzeResult(
        filename=source.name,
        transcript=transcript,
        visual=visual,
        skill=skill,
    )

    output_dir = output_dir or resolve_output_dir(skill_name=skill.skill_name, source_filename=source.name)
    emit("saving_output", 94, f"Saving files to {output_dir}…")
    output_files = save_analyze_result(result, model_name=model_name, output_dir=output_dir)
    emit("complete", 100, f"Saved {len(output_files)} files to {output_dir}")
    return result, output_dir, output_files


def analyze_result_to_dict(result: AnalyzeResult, *, model_name: str) -> dict:
    visual = result.visual
    transcript = result.transcript
    skill = result.skill

    return {
        "filename": result.filename,
        "model": model_name,
        "language": transcript.language,
        "language_probability": transcript.language_probability,
        "duration_seconds": transcript.duration,
        "text": transcript.text,
        "srt": segments_to_srt(transcript.segments),
        "segments": [
            {
                "index": segment.index,
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
            }
            for segment in transcript.segments
        ],
        "visual_analysis": None
        if visual is None
        else {
            "frames_analyzed": visual.frames_analyzed,
            "duration_seconds": visual.duration,
            "ollama_available": visual.ollama_available,
            "ollama_model": visual.ollama_model,
            "frames": [
                {
                    "timestamp": frame.timestamp,
                    "label": frame.source,
                    "scene_change": frame.scene_change,
                    "ocr_text": frame.ocr_text,
                    "description": frame.description,
                }
                for frame in visual.frames
            ],
        },
        "skill": {
            "name": skill.skill_name,
            "skill_md": skill.skill_md,
            "reference_md": skill.reference_md,
            "timeline_md": skill.timeline_md,
        },
    }
