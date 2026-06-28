# Video Knowledge Extractor

Turn videos and audio files into structured knowledge you can save as a **Cursor Agent Skill**. Combines speech transcription, computer vision, and document synthesis — all running locally.

## What it extracts

| Layer | Method | Captures |
|-------|--------|----------|
| **Speech** | Whisper (faster-whisper) | Spoken explanation, steps, reasoning |
| **On-screen text** | EasyOCR on sampled frames | Code, UI labels, slides, URLs, commands |
| **Visual context** | Optional Ollama vision (llava, moondream, etc.) | Diagrams, UI layout, actions not fully spoken |
| **Synthesis** | Timestamp merge + skill builder | `SKILL.md`, `reference.md`, `timeline.md` |

## Features

- Upload MP4, WebM, MOV, MKV, MP3, WAV, M4A, and more
- **Transcript only** mode for quick captions
- **Full analysis** mode merges audio + vision into a Cursor skill package
- Scene-change detection plus interval sampling (configurable)
- Export plain text, SRT, SKILL.md, reference.md, timeline.md

## Requirements

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/) on your PATH
- Optional: [Ollama](https://ollama.com/) with a vision model for richer frame descriptions

## Setup

```powershell
cd D:\projects\video-transcriber
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

First run downloads Whisper weights and EasyOCR models.

## Run

```powershell
python -m app.main
```

Open http://127.0.0.1:8765

## Optional: Ollama vision

For tutorial videos where visuals matter (IDE walkthroughs, diagrams, demos):

```powershell
ollama pull llava
```

Then enable **Ollama vision descriptions** in the UI. If Ollama is not running, the app still works with OCR + transcript.

## Saving as a Cursor skill

After full analysis, download:

1. `SKILL.md` — main agent instructions (put in `~/.cursor/skills/your-skill-name/SKILL.md`)
2. `reference.md` — full transcript, OCR, and merged timeline (same folder)
3. `timeline.md` — optional timestamped merge for review

Example layout:

```
~/.cursor/skills/my-tutorial/
├── SKILL.md
└── reference.md
```

Edit the generated skill before saving — tighten the description, remove noise, and add triggers specific to how you want the agent to use it.

## Model sizes (Whisper)

| Model | Speed | Accuracy |
|-------|-------|----------|
| tiny | Fastest | Lower |
| base | Good default | Balanced |
| small / medium / large-v3 | Slower | Better |

## Performance notes

- CPU-only by default. Long videos with many frames take time.
- Lower **max frames** or raise **frame interval** for faster runs.
- OCR is especially valuable for screencasts; vision LLM adds context OCR misses (layout, icons, gestures).
- GPU: edit `app/transcribe.py` and `app/video_analysis.py` to use `device="cuda"` if you have a supported NVIDIA GPU.
