# Handoff — Video Knowledge Extractor

Latest context for continuing work on [video-knowledge-extractor](https://github.com/reidlaird/video-knowledge-extractor).

## Current state (June 2026)

- **Branch:** `main`
- **Local path:** `D:\projects\video-transcriber`
- **Polish pass:** shipped in `070b62b` — speech-weighted key concepts + OCR filtering
- **Validation:** two full analysis runs on the Mobbin UI/UX tutorial — see **`docs/TEST-RESULTS.md`**

## Test outcome (short)

| Run | Folder | Verdict |
|-----|--------|---------|
| OCR only | `output/...-v3` | **Pass** — ready to use as Cursor skill |
| + moondream | `output/...-ollama-vision` | **Partial** — vision works; `SKILL.md` procedure broken by inlined hallucinated paragraphs |

**Next fix:** keep Ollama descriptions in `reference.md` only; stop embedding full vision text in `SKILL.md` procedure.

## Architecture (skill quality)

| Module | Role |
|--------|------|
| `app/ocr_filter.py` | Drop sponsor UI, demo menus, chat widgets, prices, city/state OCR |
| `app/text_analysis.py` | Speech-weighted concepts, descriptions, on-screen line scoring |
| `app/skill_builder.py` | Builds `SKILL.md`, `reference.md`, `timeline.md` |
| `tests/test_text_analysis.py` | 9 unit tests — `python -m unittest tests.test_text_analysis -v` |

Key concepts come from **transcript first**. Max 2 OCR headings; tier-1 tutorial terms pinned (hierarchy, typography, white space, signifiers, affordances, …).

## Run the app

```powershell
cd D:\projects\video-transcriber
.\.venv\Scripts\Activate.ps1
python -m app.main
```

http://127.0.0.1:8765

**Recommended for skill export:** Full analysis, OCR on, **Ollama off**.

**Ollama (optional):** models in `D:\dev\models` via Ollama’s `OLLAMA_MODELS`; app calls `http://127.0.0.1:11434`. Use model name `moondream` or `llava` in the UI — not `llava` by default unless pulled.

## Known gaps

- Vision text inlined in procedure (see test results) — **fix before recommending Ollama for skills**
- Sponsor read aloud in transcript (Marvin segment) — not filtered from speech, only OCR
- No `scripts/rebuild_skill.py` for re-synthesizing skill files from saved transcript

## Docs index

| File | Contents |
|------|----------|
| `docs/TEST-RESULTS.md` | Full run 1 vs run 2 findings |
| `README.md` | Setup, features, skill quality summary |
| `HANDOFF.md` | This file |
