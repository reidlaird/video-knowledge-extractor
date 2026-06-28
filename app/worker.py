from __future__ import annotations

import shutil
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from app.analyze import analyze_media
from app.jobs import JOB_STORE, JobStatus, JobState
from app.media import slugify
from app.output import build_result_payload, parse_output_dir, save_transcript_result
from app.transcribe import segments_to_srt, transcribe_file


@dataclass
class AnalyzeJobConfig:
    model_name: str
    language: str | None
    skill_name: str | None
    output_dir: str | None
    interval_seconds: float
    scene_threshold: float
    max_frames: int
    use_ocr: bool
    use_ollama_vision: bool
    ollama_model: str


@dataclass
class TranscribeJobConfig:
    model_name: str
    language: str | None
    output_dir: str | None


def _run_analyze_job(job: JobState, source_path: Path, config: AnalyzeJobConfig) -> None:
    work_root = Path(tempfile.mkdtemp(prefix="video-transcriber-"))
    try:
        job.update(status=JobStatus.RUNNING, stage="starting", percent=2, message="Starting analysis…")
        work_dir = work_root / "work"
        work_dir.mkdir(parents=True, exist_ok=True)

        resolved_output_dir = parse_output_dir(
            config.output_dir,
            skill_name=config.skill_name or "",
            source_filename=source_path.name,
        )

        result, output_dir, output_files = analyze_media(
            source_path,
            work_dir,
            model_name=config.model_name,
            language=config.language,
            interval_seconds=config.interval_seconds,
            scene_threshold=config.scene_threshold,
            max_frames=config.max_frames,
            use_ocr=config.use_ocr,
            use_ollama_vision=config.use_ollama_vision,
            ollama_model=config.ollama_model,
            skill_name=config.skill_name,
            output_dir=resolved_output_dir,
            on_progress=job.progress_callback(),
        )

        payload = build_result_payload(
            result,
            model_name=config.model_name,
            output_dir=output_dir,
            output_files=output_files,
        )
        job.update(
            status=JobStatus.COMPLETE,
            stage="complete",
            percent=100,
            message=f"Saved {len(output_files)} files to {output_dir}",
            result=payload,
            output_dir=str(output_dir),
            output_files=output_files,
        )
    except Exception as exc:
        job.update(
            status=JobStatus.ERROR,
            stage="error",
            percent=100,
            message="Analysis failed",
            error=str(exc),
        )
    finally:
        shutil.rmtree(work_root, ignore_errors=True)
        JOB_STORE.remove_old_jobs()


def _run_transcribe_job(job: JobState, source_path: Path, config: TranscribeJobConfig) -> None:
    try:
        progress = job.progress_callback()
        progress("transcribing", 10, "Transcribing audio with Whisper…")
        result = transcribe_file(
            source_path,
            model_name=config.model_name,
            language=config.language,
        )
        progress("transcribing", 80, "Transcription complete.")

        base_name = slugify(source_path.stem)
        output_dir = parse_output_dir(
            config.output_dir,
            skill_name=base_name,
            source_filename=source_path.name,
        )
        progress("saving_output", 92, f"Saving files to {output_dir}…")
        output_files = save_transcript_result(
            text=result.text,
            srt=segments_to_srt(result.segments),
            output_dir=output_dir,
            base_name=base_name,
        )

        payload = {
            "filename": source_path.name,
            "model": config.model_name,
            "language": result.language,
            "language_probability": result.language_probability,
            "duration_seconds": result.duration,
            "text": result.text,
            "srt": segments_to_srt(result.segments),
            "segments": [
                {
                    "index": segment.index,
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text,
                }
                for segment in result.segments
            ],
            "output_dir": str(output_dir),
            "output_files": output_files,
        }

        job.update(
            status=JobStatus.COMPLETE,
            stage="complete",
            percent=100,
            message=f"Saved {len(output_files)} files to {output_dir}",
            result=payload,
            output_dir=str(output_dir),
            output_files=output_files,
        )
    except Exception as exc:
        job.update(
            status=JobStatus.ERROR,
            stage="error",
            percent=100,
            message="Transcription failed",
            error=str(exc),
        )
    finally:
        JOB_STORE.remove_old_jobs()


def start_analyze_job(source_path: Path, config: AnalyzeJobConfig) -> JobState:
    job = JOB_STORE.create()
    thread = threading.Thread(target=_run_analyze_job, args=(job, source_path, config), daemon=True)
    thread.start()
    return job


def start_transcribe_job(source_path: Path, config: TranscribeJobConfig) -> JobState:
    job = JOB_STORE.create()
    thread = threading.Thread(target=_run_transcribe_job, args=(job, source_path, config), daemon=True)
    thread.start()
    return job


def preview_output_dir(
    *,
    skill_name: str | None,
    source_filename: str,
    output_dir: str | None = None,
) -> dict[str, str]:
    resolved = parse_output_dir(output_dir, skill_name=skill_name or "", source_filename=source_filename)
    skill_slug = slugify(skill_name or Path(source_filename).stem)
    return {
        "output_dir": str(resolved),
        "cursor_skill_path": str(Path.home() / ".cursor" / "skills" / skill_slug),
    }
