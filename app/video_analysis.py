from __future__ import annotations

import base64
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from app.jobs import ProgressCallback
from app.media import extract_frame, format_clock, is_video, probe_duration
from app.ocr_filter import filter_ocr_lines

OCR_READER = None


@dataclass
class VisualFrame:
    timestamp: float
    source: str
    ocr_text: list[str] = field(default_factory=list)
    description: str | None = None
    scene_change: bool = False


@dataclass
class VideoAnalysisResult:
    duration: float
    frames_analyzed: int
    frames: list[VisualFrame]
    ollama_available: bool
    ollama_model: str | None


def _get_ocr_reader():
    global OCR_READER
    if OCR_READER is None:
        import easyocr

        OCR_READER = easyocr.Reader(["en"], gpu=False, verbose=False)
    return OCR_READER


def _normalize_ocr_lines(lines: list[str]) -> list[str]:
    cleaned = [re.sub(r"\s+", " ", line).strip() for line in lines if line.strip()]
    return filter_ocr_lines(cleaned)


def ocr_image(image_path: Path) -> list[str]:
    reader = _get_ocr_reader()
    results = reader.readtext(str(image_path), detail=0, paragraph=True)
    return _normalize_ocr_lines([str(item) for item in results])


def _detect_scene_timestamps(source: Path, *, threshold: float) -> list[float]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        str(source),
        "-vf",
        f"select='gt(scene\\,{threshold})',showinfo",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    output = result.stderr

    timestamps: list[float] = []
    for match in re.finditer(r"pts_time:([0-9.]+)", output):
        timestamps.append(float(match.group(1)))
    return timestamps


def _dedupe_scene_timestamps(timestamps: list[float], *, min_gap: float = 5.0) -> list[float]:
    if not timestamps:
        return []

    kept: list[float] = []
    for timestamp in sorted(timestamps):
        if not kept or timestamp - kept[-1] >= min_gap:
            kept.append(timestamp)
    return kept


def _collect_frame_times(
    duration: float,
    *,
    interval_seconds: float,
    scene_timestamps: list[float],
    max_frames: int,
) -> list[tuple[float, bool]]:
    selected: dict[int, bool] = {}

    interval = max(5.0, interval_seconds)
    tick = 0.0
    while tick <= duration:
        bucket = int(round(tick))
        selected[bucket] = False
        tick += interval

    selected.setdefault(0, False)
    selected.setdefault(int(round(duration)), False)

    scene_budget = max(4, max_frames // 3)
    for timestamp in _dedupe_scene_timestamps(scene_timestamps)[:scene_budget]:
        bucket = int(round(timestamp))
        if 0 <= timestamp <= duration:
            selected[bucket] = True

    ordered = sorted(selected.items(), key=lambda item: item[0])[:max_frames]
    return [(float(seconds), scene_change) for seconds, scene_change in ordered]


def _ollama_available(base_url: str) -> bool:
    try:
        import httpx

        response = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=2.0)
        return response.status_code == 200
    except Exception:
        return False


def _describe_frame_with_ollama(
    image_path: Path,
    *,
    base_url: str,
    model: str,
) -> str | None:
    try:
        import httpx

        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        response = httpx.post(
            f"{base_url.rstrip('/')}/api/chat",
            json={
                "model": model,
                "stream": False,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "You are analyzing a frame from a tutorial or presentation video. "
                            "Describe the visible UI, diagrams, code, slides, tools, and actions. "
                            "Be concise and factual. Mention any readable text you see."
                        ),
                        "images": [encoded],
                    }
                ],
            },
            timeout=120.0,
        )
        if response.status_code != 200:
            return None
        payload = response.json()
        message = payload.get("message", {})
        content = message.get("content", "").strip()
        return content or None
    except Exception:
        return None


def analyze_video(
    source: Path,
    work_dir: Path,
    *,
    interval_seconds: float = 30.0,
    scene_threshold: float = 0.35,
    max_frames: int = 40,
    use_ocr: bool = True,
    use_ollama_vision: bool = False,
    ollama_base_url: str = "http://127.0.0.1:11434",
    ollama_model: str = "llava",
    on_progress: ProgressCallback | None = None,
) -> VideoAnalysisResult:
    if not is_video(source):
        return VideoAnalysisResult(
            duration=0.0,
            frames_analyzed=0,
            frames=[],
            ollama_available=False,
            ollama_model=None,
        )

    duration = probe_duration(source)
    scene_timestamps = _detect_scene_timestamps(source, threshold=scene_threshold)
    frame_times = _collect_frame_times(
        duration,
        interval_seconds=interval_seconds,
        scene_timestamps=scene_timestamps,
        max_frames=max_frames,
    )

    frames_dir = work_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    ollama_ready = use_ollama_vision and _ollama_available(ollama_base_url)
    active_ollama_model = ollama_model if ollama_ready else None

    frames: list[VisualFrame] = []
    total_frames = len(frame_times)
    for index, (timestamp, scene_change) in enumerate(frame_times, start=1):
        if on_progress:
            frame_percent = 45 + int((index / max(total_frames, 1)) * 35)
            on_progress(
                "analyzing_frames",
                frame_percent,
                f"Analyzing frame {index} of {total_frames}…",
            )

        frame_path = frames_dir / f"frame_{index:03d}.jpg"
        if not extract_frame(source, timestamp, frame_path):
            continue

        ocr_text: list[str] = []
        if use_ocr:
            try:
                ocr_text = ocr_image(frame_path)
            except Exception:
                ocr_text = []

        description = None
        if ollama_ready:
            description = _describe_frame_with_ollama(
                frame_path,
                base_url=ollama_base_url,
                model=ollama_model,
            )

        frames.append(
            VisualFrame(
                timestamp=timestamp,
                source=f"{format_clock(timestamp)} ({'scene change' if scene_change else 'sample'})",
                ocr_text=ocr_text,
                description=description,
                scene_change=scene_change,
            )
        )

    return VideoAnalysisResult(
        duration=duration,
        frames_analyzed=len(frames),
        frames=frames,
        ollama_available=ollama_ready,
        ollama_model=active_ollama_model,
    )
