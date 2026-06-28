from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from app.media import slugify
from app.transcribe import segments_to_srt

if TYPE_CHECKING:
    from app.analyze import AnalyzeResult

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "output"


def parse_output_dir(
    raw: str | None,
    *,
    skill_name: str,
    source_filename: str,
) -> Path:
    if raw and raw.strip():
        return Path(raw.strip()).expanduser().resolve()
    return resolve_output_dir(skill_name=skill_name, source_filename=source_filename)


def resolve_output_dir(
    *,
    skill_name: str,
    source_filename: str,
    output_root: Path | None = None,
) -> Path:
    root = output_root or DEFAULT_OUTPUT_ROOT
    folder_name = slugify(skill_name or Path(source_filename).stem)
    return root / folder_name


def list_output_files() -> list[str]:
    return [
        "SKILL.md",
        "reference.md",
        "timeline.md",
        "transcript.txt",
        "transcript.srt",
    ]


def save_analyze_result(
    result: AnalyzeResult,
    *,
    model_name: str,
    output_dir: Path,
) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    skill = result.skill
    transcript = result.transcript

    files = {
        "SKILL.md": skill.skill_md,
        "reference.md": skill.reference_md,
        "timeline.md": skill.timeline_md,
        "transcript.txt": transcript.text,
        "transcript.srt": segments_to_srt(transcript.segments),
    }

    written: list[str] = []
    for name, content in files.items():
        path = output_dir / name
        path.write_text(content, encoding="utf-8")
        written.append(name)

    return written


def save_transcript_result(
    *,
    text: str,
    srt: str,
    output_dir: Path,
    base_name: str,
) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    txt_name = f"{base_name}.txt"
    srt_name = f"{base_name}.srt"
    (output_dir / txt_name).write_text(text, encoding="utf-8")
    (output_dir / srt_name).write_text(srt, encoding="utf-8")
    return [txt_name, srt_name]


def build_result_payload(result: AnalyzeResult, *, model_name: str, output_dir: Path, output_files: list[str]) -> dict:
    from app.analyze import analyze_result_to_dict

    payload = analyze_result_to_dict(result, model_name=model_name)
    payload["output_dir"] = str(output_dir)
    payload["output_files"] = output_files
    payload["cursor_skill_path"] = str(Path.home() / ".cursor" / "skills" / result.skill.skill_name)
    return payload
