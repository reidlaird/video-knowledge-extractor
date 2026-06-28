const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const fileMeta = document.getElementById("file-meta");
const runBtn = document.getElementById("run-btn");
const clearBtn = document.getElementById("clear-btn");
const statusEl = document.getElementById("status");
const progressPanel = document.getElementById("progress-panel");
const progressStage = document.getElementById("progress-stage");
const progressPercent = document.getElementById("progress-percent");
const progressBar = document.getElementById("progress-bar");
const progressMessage = document.getElementById("progress-message");
const progressOutput = document.getElementById("progress-output");
const resultsEl = document.getElementById("results");
const skillResultsEl = document.getElementById("skill-results");
const transcriptEl = document.getElementById("transcript");
const skillPreviewEl = document.getElementById("skill-preview");
const copyBtn = document.getElementById("copy-btn");
const downloadTxtBtn = document.getElementById("download-txt-btn");
const downloadSrtBtn = document.getElementById("download-srt-btn");
const downloadSkillBtn = document.getElementById("download-skill-btn");
const downloadReferenceBtn = document.getElementById("download-reference-btn");
const downloadTimelineBtn = document.getElementById("download-timeline-btn");
const modeSelect = document.getElementById("mode");
const modelSelect = document.getElementById("model");
const languageSelect = document.getElementById("language");
const analysisOptionsEl = document.getElementById("analysis-options");
const skillNameInput = document.getElementById("skill-name");
const intervalSecondsInput = document.getElementById("interval-seconds");
const maxFramesInput = document.getElementById("max-frames");
const useOcrInput = document.getElementById("use-ocr");
const useOllamaInput = document.getElementById("use-ollama");
const ollamaModelInput = document.getElementById("ollama-model");
const outputDirInput = document.getElementById("output-dir");
const resetOutputBtn = document.getElementById("reset-output-btn");
const outputFilesPreview = document.getElementById("output-files-preview");
const cursorSkillPreview = document.getElementById("cursor-skill-preview");
const metaLanguage = document.getElementById("meta-language");
const metaConfidence = document.getElementById("meta-confidence");
const metaDuration = document.getElementById("meta-duration");
const skillMetaOutput = document.getElementById("skill-meta-output");
const skillMetaName = document.getElementById("skill-meta-name");
const skillMetaFrames = document.getElementById("skill-meta-frames");
const skillMetaVision = document.getElementById("skill-meta-vision");

const STAGE_LABELS = {
  queued: "Queued",
  starting: "Starting",
  transcribing: "Transcribing audio",
  detecting_scenes: "Detecting scenes",
  analyzing_frames: "Analyzing frames",
  building_skill: "Building skill",
  saving_output: "Saving files",
  complete: "Complete",
  error: "Failed",
};

let selectedFile = null;
let latestResult = null;
let eventSource = null;
let defaultOutputFiles = ["SKILL.md", "reference.md", "timeline.md", "transcript.txt", "transcript.srt"];
let defaultOutputRoot = "";
let outputDirCustomized = false;

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDuration(seconds) {
  const total = Math.round(seconds);
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${mins}:${String(secs).padStart(2, "0")}`;
}

function setStatus(message, type = "info") {
  statusEl.hidden = false;
  statusEl.textContent = message;
  statusEl.className = `status ${type}`;
}

function clearStatus() {
  statusEl.hidden = true;
  statusEl.textContent = "";
}

function showProgress(visible) {
  progressPanel.hidden = !visible;
}

function updateProgress(snapshot) {
  showProgress(true);
  progressStage.textContent = STAGE_LABELS[snapshot.stage] || snapshot.stage;
  progressPercent.textContent = `${snapshot.percent}%`;
  progressBar.style.width = `${snapshot.percent}%`;
  progressMessage.textContent = snapshot.message || "";
  if (snapshot.output_dir) {
    progressOutput.textContent = `Saving to: ${snapshot.output_dir}`;
  }
}

function resetProgress() {
  showProgress(false);
  progressStage.textContent = "Starting…";
  progressPercent.textContent = "0%";
  progressBar.style.width = "0%";
  progressMessage.textContent = "";
  progressOutput.textContent = "";
}

function closeEventSource() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
}

function setFile(file) {
  selectedFile = file;
  fileMeta.hidden = false;
  fileMeta.textContent = `${file.name} (${formatBytes(file.size)})`;
  runBtn.disabled = false;
  clearBtn.disabled = false;
  clearStatus();
  refreshOutputPreview();
}

function reset() {
  closeEventSource();
  selectedFile = null;
  latestResult = null;
  fileInput.value = "";
  fileMeta.hidden = true;
  fileMeta.textContent = "";
  runBtn.disabled = true;
  clearBtn.disabled = true;
  resultsEl.hidden = true;
  skillResultsEl.hidden = true;
  transcriptEl.value = "";
  skillPreviewEl.value = "";
  clearStatus();
  resetProgress();
  outputDirCustomized = false;
  outputDirInput.value = "";
  outputFilesPreview.textContent = "";
}

function downloadText(filename, content) {
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function parseError(payload, fallback) {
  const detail = payload.detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg).join(", ");
  }
  return detail || fallback;
}

function updateModeUi() {
  const analyzeMode = modeSelect.value === "analyze";
  analysisOptionsEl.hidden = !analyzeMode;
  runBtn.textContent = analyzeMode ? "Run full analysis" : "Transcribe";
  refreshOutputPreview();
}

async function refreshOutputPreview(force = false) {
  if (!selectedFile) return;
  if (outputDirCustomized && !force) return;

  const analyzeMode = modeSelect.value === "analyze";
  const params = new URLSearchParams({
    filename: selectedFile.name,
    skill_name: skillNameInput.value.trim(),
  });
  if (outputDirCustomized && outputDirInput.value.trim()) {
    params.set("output_dir", outputDirInput.value.trim());
  }

  try {
    const response = await fetch(`/api/preview-output?${params.toString()}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(parseError(payload, "Could not preview output path"));

    if (!outputDirCustomized || force) {
      outputDirInput.value = payload.output_dir;
    }
    cursorSkillPreview.textContent = payload.cursor_skill_path;
    outputFilesPreview.textContent = analyzeMode
      ? `Files: ${defaultOutputFiles.join(", ")}`
      : "Files: transcript .txt and .srt";
  } catch {
    if (!outputDirInput.value) {
      outputDirInput.placeholder = defaultOutputRoot
        ? `${defaultOutputRoot}\\my-skill-name`
        : "D:\\projects\\video-transcriber\\output\\my-skill-name";
    }
  }
}

function populateResults(payload) {
  latestResult = payload;
  transcriptEl.value = payload.text;
  metaLanguage.textContent = payload.language;
  metaConfidence.textContent = `${Math.round(payload.language_probability * 100)}%`;
  metaDuration.textContent = formatDuration(payload.duration_seconds);
  resultsEl.hidden = false;

  if (payload.skill) {
    skillPreviewEl.value = payload.skill.skill_md;
    skillMetaName.textContent = payload.skill.name;
    skillMetaFrames.textContent = payload.visual_analysis?.frames_analyzed ?? 0;
    skillMetaVision.textContent = payload.visual_analysis?.ollama_model || "OCR only";
    skillMetaOutput.textContent = payload.output_dir || "-";
    skillResultsEl.hidden = false;
  } else {
    skillResultsEl.hidden = true;
  }

  if (payload.output_dir) {
    progressOutput.textContent = `Saved to: ${payload.output_dir}`;
    outputDirInput.value = payload.output_dir;
  }
  if (payload.output_files?.length) {
    outputFilesPreview.textContent = `Saved files: ${payload.output_files.join(", ")}`;
  }
}

function watchJob(jobId, outputDir) {
  return new Promise((resolve, reject) => {
    closeEventSource();
    if (outputDir) {
      progressOutput.textContent = `Saving to: ${outputDir}`;
    }

    eventSource = new EventSource(`/api/jobs/${jobId}/events`);
    eventSource.onmessage = (event) => {
      const snapshot = JSON.parse(event.data);
      updateProgress(snapshot);

      if (snapshot.status === "complete") {
        closeEventSource();
        resolve(snapshot.result);
      }
      if (snapshot.status === "error") {
        closeEventSource();
        reject(new Error(snapshot.error || "Job failed"));
      }
    };
    eventSource.onerror = () => {
      closeEventSource();
      reject(new Error("Lost connection to progress stream"));
    };
  });
}

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    fileInput.click();
  }
});

dropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropzone.classList.add("dragover");
});

dropzone.addEventListener("dragleave", () => {
  dropzone.classList.remove("dragover");
});

dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropzone.classList.remove("dragover");
  const file = event.dataTransfer.files[0];
  if (file) setFile(file);
});

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  if (file) setFile(file);
});

modeSelect.addEventListener("change", updateModeUi);
skillNameInput.addEventListener("input", () => refreshOutputPreview());
outputDirInput.addEventListener("input", () => {
  outputDirCustomized = true;
});
resetOutputBtn.addEventListener("click", () => {
  outputDirCustomized = false;
  refreshOutputPreview(true);
});
clearBtn.addEventListener("click", reset);

runBtn.addEventListener("click", async () => {
  if (!selectedFile) return;

  const analyzeMode = modeSelect.value === "analyze";
  runBtn.disabled = true;
  clearBtn.disabled = true;
  resultsEl.hidden = true;
  skillResultsEl.hidden = true;
  clearStatus();
  resetProgress();
  showProgress(true);
  updateProgress({
    stage: "starting",
    percent: 1,
    message: analyzeMode
      ? "Uploading file and starting full analysis…"
      : "Uploading file and starting transcription…",
  });

  const formData = new FormData();
  formData.append("file", selectedFile);
  formData.append("model", modelSelect.value);
  formData.append("language", languageSelect.value);
  formData.append("output_dir", outputDirInput.value.trim());

  if (analyzeMode) {
    formData.append("skill_name", skillNameInput.value.trim());
    formData.append("interval_seconds", intervalSecondsInput.value);
    formData.append("scene_threshold", "0.35");
    formData.append("max_frames", maxFramesInput.value);
    formData.append("use_ocr", useOcrInput.checked ? "true" : "false");
    formData.append("use_ollama_vision", useOllamaInput.checked ? "true" : "false");
    formData.append("ollama_model", ollamaModelInput.value.trim() || "llava");
  }

  const endpoint = analyzeMode ? "/api/jobs/analyze" : "/api/jobs/transcribe";

  try {
    const response = await fetch(endpoint, { method: "POST", body: formData });
    const created = await response.json();
    if (!response.ok) {
      throw new Error(parseError(created, analyzeMode ? "Analysis failed" : "Transcription failed"));
    }

    outputDirInput.value = created.output_dir;
    if (created.cursor_skill_path) {
      cursorSkillPreview.textContent = created.cursor_skill_path;
    }
    progressOutput.textContent = `Saving to: ${created.output_dir}`;

    const payload = await watchJob(created.job_id, created.output_dir);
    populateResults(payload);
    setStatus(
      analyzeMode
        ? `Analysis complete. Files saved to ${payload.output_dir}`
        : `Transcription complete. Files saved to ${payload.output_dir}`,
      "success"
    );
  } catch (error) {
    setStatus(error.message, "error");
    updateProgress({ stage: "error", percent: 100, message: error.message });
  } finally {
    runBtn.disabled = !selectedFile;
    clearBtn.disabled = !selectedFile;
  }
});

copyBtn.addEventListener("click", async () => {
  if (!latestResult?.text) return;
  await navigator.clipboard.writeText(latestResult.text);
  setStatus("Copied transcript to clipboard.", "success");
});

downloadTxtBtn.addEventListener("click", () => {
  if (!latestResult?.text || !selectedFile) return;
  const baseName = selectedFile.name.replace(/\.[^.]+$/, "");
  downloadText(`${baseName}.txt`, latestResult.text);
});

downloadSrtBtn.addEventListener("click", () => {
  if (!latestResult?.srt || !selectedFile) return;
  const baseName = selectedFile.name.replace(/\.[^.]+$/, "");
  downloadText(`${baseName}.srt`, latestResult.srt);
});

downloadSkillBtn.addEventListener("click", () => {
  if (!latestResult?.skill?.skill_md) return;
  downloadText("SKILL.md", latestResult.skill.skill_md);
});

downloadReferenceBtn.addEventListener("click", () => {
  if (!latestResult?.skill?.reference_md) return;
  downloadText("reference.md", latestResult.skill.reference_md);
});

downloadTimelineBtn.addEventListener("click", () => {
  if (!latestResult?.skill?.timeline_md) return;
  downloadText("timeline.md", latestResult.skill.timeline_md);
});

async function loadOutputInfo() {
  try {
    const response = await fetch("/api/output-info");
    const payload = await response.json();
    if (response.ok) {
      defaultOutputFiles = payload.default_files;
      defaultOutputRoot = payload.default_output_root;
      outputDirInput.placeholder = `${defaultOutputRoot}\\my-skill-name`;
    }
  } catch {
    // keep defaults
  }
}

loadOutputInfo();
updateModeUi();
reset();
