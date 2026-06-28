from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from faster_whisper import WhisperModel

from app.media import AUDIO_EXTENSIONS, SUPPORTED_EXTENSIONS, extract_audio

MODEL_CACHE: dict[str, WhisperModel] = {}


@dataclass
class TranscriptSegment:
    index: int
    start: float
    end: float
    text: str


@dataclass
class TranscriptResult:
    language: str
    language_probability: float
    duration: float
    text: str
    segments: list[TranscriptSegment]


def get_model(model_name: str) -> WhisperModel:
    if model_name not in MODEL_CACHE:
        MODEL_CACHE[model_name] = WhisperModel(model_name, device="cpu", compute_type="int8")
    return MODEL_CACHE[model_name]


def _format_timestamp(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds % 1) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def segments_to_srt(segments: list[TranscriptSegment]) -> str:
    lines: list[str] = []
    for segment in segments:
        lines.append(str(segment.index))
        lines.append(f"{_format_timestamp(segment.start)} --> {_format_timestamp(segment.end)}")
        lines.append(segment.text.strip())
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def prepare_audio(source: Path, work_dir: Path) -> Path:
    if source.suffix.lower() in AUDIO_EXTENSIONS:
        audio_path = work_dir / f"audio{source.suffix.lower()}"
        audio_path.write_bytes(source.read_bytes())
        return audio_path

    audio_path = work_dir / "audio.wav"
    extract_audio(source, audio_path)
    return audio_path


def transcribe_file(
    source: Path,
    *,
    model_name: str = "base",
    language: str | None = None,
) -> TranscriptResult:
    suffix = source.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(f"Unsupported file type '{suffix}'. Supported: {supported}")

    with tempfile.TemporaryDirectory() as temp_dir:
        audio_path = prepare_audio(source, Path(temp_dir))
        model = get_model(model_name)
        segments_iter, info = model.transcribe(
            str(audio_path),
            language=language or None,
            vad_filter=True,
        )

        segments: list[TranscriptSegment] = []
        text_parts: list[str] = []
        for index, segment in enumerate(segments_iter, start=1):
            cleaned = segment.text.strip()
            if not cleaned:
                continue
            segments.append(
                TranscriptSegment(
                    index=index,
                    start=segment.start,
                    end=segment.end,
                    text=cleaned,
                )
            )
            text_parts.append(cleaned)

    return TranscriptResult(
        language=info.language or "unknown",
        language_probability=float(info.language_probability or 0.0),
        duration=float(info.duration or 0.0),
        text=" ".join(text_parts),
        segments=segments,
    )
