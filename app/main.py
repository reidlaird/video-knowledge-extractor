from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.analyze import analyze_media
from app.jobs import JOB_STORE, JobStatus, dumps_event
from app.output import DEFAULT_OUTPUT_ROOT, build_result_payload, list_output_files, parse_output_dir
from app.transcribe import SUPPORTED_EXTENSIONS, segments_to_srt, transcribe_file
from app.worker import AnalyzeJobConfig, TranscribeJobConfig, preview_output_dir, start_analyze_job, start_transcribe_job

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR.parent / "static"

app = FastAPI(title="Video Transcriber", version="1.2.0")

WHISPER_MODELS = {"tiny", "base", "small", "medium", "large-v3"}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/formats")
def formats() -> dict[str, list[str]]:
    return {"extensions": sorted(ext.lstrip(".") for ext in SUPPORTED_EXTENSIONS)}


@app.get("/api/output-info")
def output_info() -> dict:
    return {
        "default_output_root": str(DEFAULT_OUTPUT_ROOT),
        "default_files": list_output_files(),
        "cursor_skills_root": str(Path.home() / ".cursor" / "skills"),
    }


@app.get("/api/preview-output")
def preview_output(
    filename: str = Query(...),
    skill_name: str = Query(default=""),
    output_dir: str = Query(default=""),
) -> dict[str, str]:
    return preview_output_dir(
        skill_name=skill_name.strip() or None,
        source_filename=filename,
        output_dir=output_dir.strip() or None,
    )


def _validate_upload(file: UploadFile, contents: bytes) -> Path:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    return Path(file.filename)


def _validate_whisper_model(model: str) -> None:
    if model not in WHISPER_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported model '{model}'. Choose one of: {', '.join(sorted(WHISPER_MODELS))}",
        )


def _persist_upload(contents: bytes, filename: Path) -> Path:
    upload_root = Path(tempfile.mkdtemp(prefix="video-transcriber-upload-"))
    source_path = upload_root / filename.name
    source_path.write_bytes(contents)
    return source_path


@app.post("/api/jobs/analyze")
async def create_analyze_job(
    file: UploadFile = File(...),
    model: str = Form(default="base"),
    language: str = Form(default=""),
    skill_name: str = Form(default=""),
    interval_seconds: float = Form(default=30.0),
    scene_threshold: float = Form(default=0.35),
    max_frames: int = Form(default=40),
    use_ocr: bool = Form(default=True),
    use_ollama_vision: bool = Form(default=False),
    ollama_model: str = Form(default="llava"),
    output_dir: str = Form(default=""),
) -> dict:
    contents = await file.read()
    filename = _validate_upload(file, contents)
    _validate_whisper_model(model)

    if interval_seconds < 5 or interval_seconds > 300:
        raise HTTPException(status_code=400, detail="interval_seconds must be between 5 and 300")
    if scene_threshold < 0.05 or scene_threshold > 0.95:
        raise HTTPException(status_code=400, detail="scene_threshold must be between 0.05 and 0.95")
    if max_frames < 5 or max_frames > 120:
        raise HTTPException(status_code=400, detail="max_frames must be between 5 and 120")

    source_path = _persist_upload(contents, filename)
    preview = preview_output_dir(
        skill_name=skill_name.strip() or None,
        source_filename=file.filename or filename.name,
        output_dir=output_dir.strip() or None,
    )
    job = start_analyze_job(
        source_path,
        AnalyzeJobConfig(
            model_name=model,
            language=language.strip() or None,
            skill_name=skill_name.strip() or None,
            output_dir=output_dir.strip() or None,
            interval_seconds=interval_seconds,
            scene_threshold=scene_threshold,
            max_frames=max_frames,
            use_ocr=use_ocr,
            use_ollama_vision=use_ollama_vision,
            ollama_model=ollama_model.strip() or "llava",
        ),
    )

    return {
        "job_id": job.job_id,
        "output_dir": preview["output_dir"],
        "cursor_skill_path": preview["cursor_skill_path"],
        "output_files": list_output_files(),
    }


@app.post("/api/jobs/transcribe")
async def create_transcribe_job(
    file: UploadFile = File(...),
    model: str = Form(default="base"),
    language: str = Form(default=""),
    output_dir: str = Form(default=""),
) -> dict:
    contents = await file.read()
    filename = _validate_upload(file, contents)
    _validate_whisper_model(model)

    source_path = _persist_upload(contents, filename)
    preview = preview_output_dir(
        skill_name=None,
        source_filename=file.filename or filename.name,
        output_dir=output_dir.strip() or None,
    )
    job = start_transcribe_job(
        source_path,
        TranscribeJobConfig(
            model_name=model,
            language=language.strip() or None,
            output_dir=output_dir.strip() or None,
        ),
    )

    return {
        "job_id": job.job_id,
        "output_dir": preview["output_dir"],
        "output_files": [f"{Path(file.filename or filename.name).stem}.txt", f"{Path(file.filename or filename.name).stem}.srt"],
    }


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = JOB_STORE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.snapshot()


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str) -> StreamingResponse:
    job = JOB_STORE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_stream():
        last_payload = ""
        while True:
            snapshot = job.snapshot()
            payload = json.dumps(snapshot)
            if payload != last_payload:
                yield dumps_event(snapshot)
                last_payload = payload

            if snapshot["status"] in {JobStatus.COMPLETE.value, JobStatus.ERROR.value}:
                break
            await asyncio.sleep(0.4)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    model: str = Form(default="base"),
    language: str = Form(default=""),
) -> dict:
    contents = await file.read()
    filename = _validate_upload(file, contents)
    _validate_whisper_model(model)

    with tempfile.TemporaryDirectory() as temp_dir:
        source_path = Path(temp_dir) / filename.name
        source_path.write_bytes(contents)

        try:
            result = transcribe_file(
                source_path,
                model_name=model,
                language=language.strip() or None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "filename": file.filename,
        "model": model,
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
    }


@app.post("/api/analyze")
async def analyze(
    file: UploadFile = File(...),
    model: str = Form(default="base"),
    language: str = Form(default=""),
    skill_name: str = Form(default=""),
    interval_seconds: float = Form(default=30.0),
    scene_threshold: float = Form(default=0.35),
    max_frames: int = Form(default=40),
    use_ocr: bool = Form(default=True),
    use_ollama_vision: bool = Form(default=False),
    ollama_model: str = Form(default="llava"),
    output_dir: str = Form(default=""),
) -> dict:
    contents = await file.read()
    filename = _validate_upload(file, contents)
    _validate_whisper_model(model)

    if interval_seconds < 5 or interval_seconds > 300:
        raise HTTPException(status_code=400, detail="interval_seconds must be between 5 and 300")
    if scene_threshold < 0.05 or scene_threshold > 0.95:
        raise HTTPException(status_code=400, detail="scene_threshold must be between 0.05 and 0.95")
    if max_frames < 5 or max_frames > 120:
        raise HTTPException(status_code=400, detail="max_frames must be between 5 and 120")

    with tempfile.TemporaryDirectory() as temp_dir:
        source_path = Path(temp_dir) / filename.name
        source_path.write_bytes(contents)
        work_dir = Path(temp_dir) / "work"
        work_dir.mkdir(parents=True, exist_ok=True)

        try:
            resolved_output_dir = parse_output_dir(
                output_dir.strip() or None,
                skill_name=skill_name.strip() or "",
                source_filename=filename.name,
            )
            result, saved_output_dir, output_files = analyze_media(
                source_path,
                work_dir,
                model_name=model,
                language=language.strip() or None,
                interval_seconds=interval_seconds,
                scene_threshold=scene_threshold,
                max_frames=max_frames,
                use_ocr=use_ocr,
                use_ollama_vision=use_ollama_vision,
                ollama_model=ollama_model.strip() or "llava",
                skill_name=skill_name.strip() or None,
                output_dir=resolved_output_dir,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    payload = build_result_payload(
        result,
        model_name=model,
        output_dir=saved_output_dir,
        output_files=output_files,
    )
    return payload


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8765, reload=False)


if __name__ == "__main__":
    run()
