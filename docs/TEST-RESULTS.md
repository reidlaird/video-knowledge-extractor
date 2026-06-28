# Test results — UI/UX tutorial video (June 2026)

Full analysis on **Every UI⧸UX Concept Explained in Under 10 Minutes.mp4** (9:23, English). Two runs on the same source: OCR-only baseline, then OCR + Ollama vision (`moondream`).

Output folders are gitignored; paths are local only.

## Runs

| Run | Output folder | Ollama | Model |
|-----|---------------|--------|-------|
| 1 — baseline | `output/every-ui-ux-concept-explained-in-under-10-minute-v3` | Off | — |
| 2 — vision | `output/every-ui-ux-concept-explained-in-under-10-minute-ollama-vision` | On | `moondream` |

Commit under test: `070b62b` (speech-weighted concepts + OCR filtering).

## Summary

| Criterion | Run 1 (OCR only) | Run 2 (+ moondream) |
|-----------|------------------|---------------------|
| **Ship as Cursor skill?** | **Yes** | **No** (without manual edits) |
| Key concepts | Pass | Pass (unchanged) |
| Description | Pass | Pass (unchanged) |
| Procedure in `SKILL.md` | Pass | **Fail** — full vision paragraphs inlined |
| `reference.md` OCR noise | Pass — no menu/sponsor strings | OCR still filtered; vision text reintroduces demo descriptions |
| Ollama integration | N/A | Connected — 32 frames described |

**Conclusion:** The polish pass (speech + OCR filtering) is validated on a fresh full run. Ollama vision works but **must not dump raw model output into `SKILL.md` procedure** — moondream hallucinates on small tutorial frames and makes the skill unusable.

---

## Run 1 — OCR + transcript only (PASS)

### Key concepts

```
hierarchy, typography, white space, signifiers, affordances, dark mode, shadows, micro interactions
```

All from speech-weighted extraction. No Burrito Bowl, cocktail menus, or sponsor UI.

### Description (frontmatter)

Readable Cursor skill trigger listing domain terms. Example:

> Explains Every UI/UX Concept Explained in Under 10 Minutes including hierarchy, typography, white space, signifiers, affordances, dark mode. Use when the user asks about hierarchy, typography, white space, signifiers, UI/UX design patterns, or guidance from this tutorial.

### Procedure

12 concise steps. On-screen citations only where useful:

- **0:15** — `(On-screen: Affordances & Signifiers)`
- **2:45** — `(On-screen: letting things breathe)`

No `Drinks`, `Dessert`, `Burrito Bowl`, or city demo labels in procedure.

### reference.md

OCR filtering confirmed: grep for `Burrito`, `Drinks`, `Negroni`, `Mushroom` — **no matches** in filtered OCR output.

**Recommendation:** Use this output (or equivalent OCR-only runs) when copying to `~/.cursor/skills/`.

---

## Run 2 — OCR + transcript + moondream (PARTIAL)

### What worked

- Ollama API reachable; vision ran on all 32 sampled frames.
- **Key concepts** and **description** identical to run 1 — vision does not drive concept extraction (intended).
- Vision notes appear in `reference.md` under `## Visual frame notes` (useful as optional deep context).

### What failed

Full moondream responses are embedded in **`SKILL.md` → Procedure** as `(Visual: …)` suffixes. Step 1 is a multi-paragraph essay; later steps repeat the pattern.

**Problems with inlined vision text:**

1. **Hallucinations** on low-res frames — e.g. French slide titles (“Après les définitions”), fake YouTube chrome, invented sites (`JimmyO'Shea.com`, `thecodingdevelopers.com`), wrong prices ($6.50 vs actual demo UI).
2. **Demo noise returns** via vision prose (Drinks Menu, Burrito Bowl, Jamesville/Syracuse) even though OCR filtering removed those strings from run 1.
3. **`SKILL.md` too large and unreliable** for agent consumption — contradicts the goal of a tight Cursor skill.

Example (step 2, abbreviated): vision describes a YouTube interface and French subtitles instead of the Figma slide showing “Affordances & Signifiers”.

### reference.md

OCR sections remain cleaner than pre-polish runs, but **Vision:** blocks contain the same hallucinated demo descriptions (Burrito Bowl, Drinks Menu, etc.).

---

## Recommendations

### For users today

1. **Export skills with Ollama vision unchecked** for tutorial/screencast videos like this one.
2. Use run 1-style output for `SKILL.md` + `reference.md` in `~/.cursor/skills/`.
3. If experimenting with vision, compare output folders side by side before publishing a skill.

### For next code change

| Priority | Change |
|----------|--------|
| **P0** | Do not inline full vision text in `SKILL.md` procedure — keep vision in `reference.md` / `timeline.md` only |
| **P1** | If procedure needs vision hint: one-line summary, max ~120 chars, or omit when confidence is low |
| **P2** | UI copy: warn that vision enriches reference docs, not the main skill file |
| **P3** | Evaluate `llava` vs `moondream` on same video after P0; smaller models may still hallucinate on compressed frames |

---

## Reproduce

```powershell
cd D:\projects\video-transcriber
.\.venv\Scripts\Activate.ps1
python -m app.main
```

Open http://127.0.0.1:8765 → **Full analysis + skill export**.

**Run 1:** OCR on, Ollama off.  
**Run 2:** OCR on, Ollama on, model `moondream` (requires `ollama serve` and `ollama pull moondream`).

Unit tests:

```powershell
python -m unittest tests.test_text_analysis -v
```

---

## Related docs

- `HANDOFF.md` — implementation notes and next-session context
- `README.md` — setup, skill quality overview, Ollama optional use
