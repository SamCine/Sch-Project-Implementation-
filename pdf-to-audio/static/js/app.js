/**
 * PDF to Audio — ElevenLabs Edition
 * Frontend App
 */

// ── State ──────────────────────────────────────────────────────────────────
const state = {
  apiKey:               "",
  apiKeyValid:          false,
  fileId:               null,
  metadata:             null,
  chapters:             [],
  selectedChapterIndex: -1,
  currentJobId:         null,
  pollingInterval:      null,
};

const $ = (id) => document.getElementById(id);

// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  setupApiKey();
  setupUpload();
  setupControls();
  setupConvertBtn();
  loadSavedKey();
});

// ── API Key ────────────────────────────────────────────────────────────────
function loadSavedKey() {
  // Check localStorage first, then migrate old sessionStorage key if present
  let saved = localStorage.getItem("el_api_key");
  if (!saved) {
    // Migrate from old sessionStorage (before the fix)
    const legacy = sessionStorage.getItem("el_api_key");
    if (legacy) {
      saved = legacy;
      localStorage.setItem("el_api_key", legacy);
      sessionStorage.removeItem("el_api_key");
    }
  }
  if (saved) {
    $("api-key-input").value = saved;
    state.apiKey      = saved;
    state.apiKeyValid = true;
    // silently re-validate with server so session key is set
    silentValidate(saved);
  }
}

async function silentValidate(key) {
  try {
    const res = await fetch("/api/validate-key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: key }),
    });
    const data = await res.json();
    if (data.valid) {
      state.apiKey      = key;
      state.apiKeyValid = true;
      // update usage bar if visible
      if (data.user_info) {
        const { character_count, character_limit, tier } = data.user_info;
        const pct = Math.min(100, (character_count / character_limit) * 100);
        const status = $("key-status");
        status.className     = "key-status valid";
        status.style.display = "block";
        status.innerHTML     = `✅ API key valid! &nbsp;|&nbsp; Plan: <strong>${tier}</strong>`;
        $("usage-wrap").style.display = "block";
        $("usage-text").textContent   = `${character_count.toLocaleString()} / ${character_limit.toLocaleString()}`;
        $("usage-bar").style.width    = pct + "%";
      }
      await loadVoices(key);
      updateConvertBtn();
    } else {
      // key is no longer valid, clear it
      state.apiKey = "";
      state.apiKeyValid = false;
      localStorage.removeItem("el_api_key");
      updateConvertBtn();
    }
  } catch(e) {
    // network error — keep state as-is, don't block user
    console.warn("Silent validate failed:", e);
  }
}

function setupApiKey() {
  // Toggle visibility
  $("toggle-key-vis").addEventListener("click", () => {
    const inp = $("api-key-input");
    inp.type = inp.type === "password" ? "text" : "password";
  });

  // Validate on Enter
  $("api-key-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") validateApiKey();
  });

  $("validate-btn").addEventListener("click", validateApiKey);
}

async function validateApiKey() {
  const key = $("api-key-input").value.trim();
  if (!key) {
    showToast("Please enter your ElevenLabs API key.", "warning");
    return;
  }

  if (key.startsWith("sk-")) {
    showToast("That looks like an OpenAI key. Use your ElevenLabs API key instead.", "error");
    return;
  }

  $("validate-btn").disabled = true;
  $("validate-btn").innerHTML = '<span class="spinner"></span>';

  const status = $("key-status");
  status.style.display = "none";

  try {
    const res  = await fetch("/api/validate-key", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ api_key: key }),
    });
    const data = await res.json();

    if (data.valid) {
      state.apiKey      = key;
      state.apiKeyValid = true;
      localStorage.setItem("el_api_key", key);

      status.className     = "key-status valid";
      status.style.display = "block";

      // Show usage
      if (data.user_info) {
        const { character_count, character_limit, tier } = data.user_info;
        const pct = Math.min(100, (character_count / character_limit) * 100);
        status.innerHTML =
          `✅ API key valid! &nbsp;|&nbsp; Plan: <strong>${tier}</strong>`;
        $("usage-wrap").style.display = "block";
        $("usage-text").textContent   = `${character_count.toLocaleString()} / ${character_limit.toLocaleString()}`;
        $("usage-bar").style.width    = pct + "%";
      } else {
        status.innerHTML = "✅ API key valid!";
      }

      showToast("API key validated!", "success");
      await loadVoices(key);
      updateConvertBtn();
    } else {
      state.apiKeyValid        = false;
      status.className         = "key-status invalid";
      status.style.display     = "block";
      status.innerHTML         = "❌ " + (data.message || "Invalid API key.");
      showToast(data.message || "Invalid API key.", "error");
      updateConvertBtn();
    }
  } catch (e) {
    showToast("Validation error: " + e.message, "error");
  } finally {
    $("validate-btn").disabled = false;
    $("validate-btn").innerHTML = "Validate Key";
  }
}

// ── Voices ─────────────────────────────────────────────────────────────────
async function loadVoices(apiKey) {
  try {
    const res  = await fetch("/api/voices", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ api_key: apiKey }),
    });
    const data = await res.json();

    // Populate voice select
    const vSel = $("voice-select");
    vSel.innerHTML = "";
    data.voices.forEach((v) => {
      const opt = document.createElement("option");
      opt.value       = v.voice_id;
      opt.textContent = v.name;
      // Default: Rachel
      if (v.voice_id === "pNInz6obpgDQGcFmaJgB") opt.selected = true;
      vSel.appendChild(opt);
    });

    // Populate model select
    const mSel = $("model-select");
    mSel.innerHTML = "";
    data.models.forEach((m) => {
      const opt = document.createElement("option");
      opt.value       = m.model_id;
      opt.textContent = m.label;
      if (m.model_id === "eleven_multilingual_v2") opt.selected = true;
      mSel.appendChild(opt);
    });

    $("preview-btn").disabled = false;
    showToast(`Loaded ${data.voices.length} voices.`, "success");
  } catch (e) {
    showToast("Could not load voices: " + e.message, "error");
  }
}

// Voice preview
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("preview-btn")?.addEventListener("click", previewVoice);
});

async function previewVoice() {
  if (!state.apiKeyValid) {
    showToast("Please validate your API key first.", "warning");
    return;
  }
  const voiceId = $("voice-select").value;
  const modelId = $("model-select").value;
  if (!voiceId) return;

  $("preview-btn").disabled = true;
  $("preview-btn").innerHTML = '<span class="spinner"></span>';

  try {
    const res = await fetch("/api/convert", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        file_id:          "__preview__",
        api_key:          state.apiKey,
        voice_id:         voiceId,
        model_id:         modelId,
        stability:        parseFloat($("stability-slider").value),
        similarity_boost: parseFloat($("similarity-slider").value),
        style:            parseFloat($("style-slider").value),
        speed:            1.0,
        pitch:            0,
        preview:          true,
        preview_text:     "Hello! This is a preview of the selected voice. How does it sound?",
      }),
    });
    const data = await res.json();

    if (data.job_id) {
      pollPreview(data.job_id);
    } else {
      showToast(data.error || "Preview failed.", "error");
      resetPreviewBtn();
    }
  } catch (e) {
    showToast("Preview error: " + e.message, "error");
    resetPreviewBtn();
  }
}

function pollPreview(jobId) {
  const interval = setInterval(async () => {
    try {
      const res = await fetch(`/api/job/${jobId}`);
      const job = await res.json();
      if (job.status === "done") {
        clearInterval(interval);
        resetPreviewBtn();
        const audio = new Audio(`/api/audio/${job.output_path}`);
        audio.play();
        showToast("Playing preview...", "info");
      } else if (job.status === "failed") {
        clearInterval(interval);
        resetPreviewBtn();
        showToast("Preview failed: " + (job.error || "Unknown"), "error");
      }
    } catch (e) {
      clearInterval(interval);
      resetPreviewBtn();
    }
  }, 1200);
}

function resetPreviewBtn() {
  $("preview-btn").disabled = false;
  $("preview-btn").innerHTML = "▶ Preview";
}

// ── Upload ─────────────────────────────────────────────────────────────────
function setupUpload() {
  const zone  = $("upload-zone");
  const input = $("file-input");

  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    zone.classList.add("drag-over");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    if (e.dataTransfer.files.length > 0) handleFile(e.dataTransfer.files[0]);
  });

  input.addEventListener("change", (e) => {
    if (e.target.files.length > 0) handleFile(e.target.files[0]);
  });
}

async function handleFile(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    showToast("Only PDF files are supported.", "error");
    return;
  }

  const fileInfo        = document.querySelector(".file-info");
  fileInfo.textContent  = `📄 ${file.name} (${formatBytes(file.size)})`;
  fileInfo.style.display = "block";

  showToast("Uploading PDF...", "info");
  setUploadLoading(true);

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res  = await fetch("/api/upload", { method: "POST", body: formData });
    const data = await res.json();

    if (!res.ok) {
      showToast(data.error || "Upload failed.", "error");
      return;
    }

    state.fileId               = data.file_id;
    state.metadata             = data.metadata;
    state.chapters             = data.chapters || [];
    state.selectedChapterIndex = -1;

    renderPDFInfo(data.metadata);
    renderChapters(state.chapters);
    showSections();
    updateConvertBtn(); // Explicitly update button state
    
    showToast(
      `✅ PDF loaded! ${data.metadata.total_pages} pages (detecting sections...)`,
      "success"
    );

    // Start polling for chapters if not immediately available
    if (state.chapters.length === 0) {
      showChaptersLoading(true);
      pollForChapters(data.file_id);
    }
  } catch (e) {
    showToast("Upload error: " + e.message, "error");
  } finally {
    setUploadLoading(false);
  }
}

async function pollForChapters(fileId) {
  // Poll for up to 30 seconds for chapters to be detected
  for (let i = 0; i < 60; i++) {
    try {
      const res = await fetch(`/api/chapters/${fileId}`);
      const data = await res.json();
      
      if (data.chapters && data.chapters.length > 0) {
        state.chapters = data.chapters;
        showChaptersLoading(false);
        renderChapters(data.chapters);
        showToast("✅ Sections detected!", "success");
        return;
      }
      
      if (data.ready === false && i === 59) {
        // Timeout — show "no sections" fallback
        showChaptersLoading(false);
        showChaptersEmpty(true);
        showToast("⚠️ No sections found — full document will be used.", "warning");
        return;
      }
    } catch (e) {
      console.error("Error polling chapters:", e);
    }
    
    // Wait before next poll (0.5 seconds)
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  // Final fallback
  showChaptersLoading(false);
  showChaptersEmpty(true);
}

function showChaptersLoading(on) {
  const el = document.getElementById("chapters-loading");
  if (el) el.style.display = on ? "flex" : "none";
  if (on) showChaptersEmpty(false);
}

function showChaptersEmpty(on) {
  const el = document.getElementById("chapters-empty");
  if (el) el.style.display = on ? "block" : "none";
}

function setUploadLoading(on) {
  const zone            = $("upload-zone");
  zone.style.opacity    = on ? "0.6" : "1";
  zone.style.pointerEvents = on ? "none" : "auto";
}

function renderPDFInfo(meta) {
  const info   = $("pdf-info");
  info.innerHTML =
    `<div class="pdf-meta">
       <h3>${escapeHtml(meta.title || "Untitled Document")}</h3>
       <p>by <strong>${escapeHtml(meta.author || "Unknown Author")}</strong></p>
       ${meta.subject ? `<p style="margin-top:0.25rem;color:var(--text-muted);font-size:0.85rem">${escapeHtml(meta.subject)}</p>` : ""}
     </div>
     <div style="display:flex;gap:0.5rem;flex-wrap:wrap;align-items:flex-start;margin-top:0.5rem">
       <span class="badge">📄 ${meta.total_pages} pages</span>
     </div>`;
  info.classList.add("visible");
}

function renderChapters(chapters) {
  showChaptersLoading(false);
  showChaptersEmpty(chapters.length === 0);
  const list    = $("chapter-list");
  list.innerHTML = "";

  const allItem = document.createElement("div");
  allItem.className     = "chapter-select-all selected";
  allItem.dataset.index = -1;
  allItem.innerHTML     = `<span>📚 Convert entire document</span>`;
  allItem.addEventListener("click", () => selectChapter(-1, allItem));
  list.appendChild(allItem);

  chapters.forEach((ch, i) => {
    const item         = document.createElement("div");
    item.className     = "chapter-item";
    item.dataset.index = i;
    item.innerHTML     =
      `<span class="chapter-title">${escapeHtml(ch.title)}</span>
       <span class="chapter-pages">pp. ${ch.start_page}–${ch.end_page}</span>`;
    item.addEventListener("click", () => selectChapter(i, item));
    list.appendChild(item);
  });
}

function selectChapter(index, element) {
  state.selectedChapterIndex = index;
  document.querySelectorAll(".chapter-item, .chapter-select-all")
    .forEach((el) => el.classList.remove("selected"));
  element.classList.add("selected");
}

function showSections() {
  $("settings-section").classList.add("visible");
  $("chapters-section").classList.add("visible");
  $("convert-section").classList.add("visible");
  updateConvertBtn();
}

// ── Controls ───────────────────────────────────────────────────────────────
function setupControls() {
  const sliders = [
    ["stability-slider",  "stability-val",  (v) => parseFloat(v).toFixed(2)],
    ["similarity-slider", "similarity-val", (v) => parseFloat(v).toFixed(2)],
    ["style-slider",      "style-val",      (v) => parseFloat(v).toFixed(2)],
    ["speed-slider",      "speed-val",      (v) => parseFloat(v).toFixed(1) + "×"],
    ["pitch-slider",      "pitch-val",      (v) => { const n = parseInt(v); return (n > 0 ? "+" : "") + n + " st"; }],
  ];

  sliders.forEach(([sliderId, valId, fmt]) => {
    const slider = $(sliderId);
    if (slider) {
      slider.addEventListener("input", () => {
        $(valId).textContent = fmt(slider.value);
      });
    }
  });
}

// ── Convert Button ─────────────────────────────────────────────────────────
function updateConvertBtn() {
  const ready = state.apiKeyValid && state.fileId;
  const btn = $("convert-btn");
  
  if (ready) {
    btn.disabled = false;
    btn.innerHTML = "🎙️ Convert to Audio";
    btn.style.opacity = "1";
    btn.style.cursor = "pointer";
    btn.title = "Ready! Click to convert your PDF to audio";
    btn.classList.add("ready");
    btn.classList.remove("disabled");
  } else {
    btn.disabled = true;
    btn.innerHTML = "🎙️ Convert to Audio";
    btn.style.opacity = "0.45";
    btn.style.cursor = "not-allowed";
    btn.title = "Upload a PDF and validate your API key to enable conversion";
    btn.classList.remove("ready");
    btn.classList.add("disabled");
  }
}

function setupConvertBtn() {
  $("convert-btn").addEventListener("click", startConversion);

  $("convert-again-btn")?.addEventListener("click", () => {
    hideAudioPlayer();
    $("convert-section").scrollIntoView({ behavior: "smooth" });
  });
}

async function startConversion() {
  // Safety net: if state lost the key (e.g. page reload), recover from localStorage
  if (!state.apiKey) {
    const saved = localStorage.getItem("el_api_key");
    if (saved) {
      state.apiKey      = saved;
      state.apiKeyValid = true;
    }
  }
  if (!state.apiKeyValid) {
    showToast("Please validate your API key first.", "warning");
    return;
  }
  if (!state.fileId) {
    showToast("Please upload a PDF first.", "warning");
    return;
  }

  $("convert-btn").disabled = true;
  $("convert-btn").innerHTML = `<span class="spinner"></span> Converting...`;

  showProgress();
  hideAudioPlayer();

  try {
    const res  = await fetch("/api/convert", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        file_id:          state.fileId,
        api_key:          state.apiKey,
        voice_id:         $("voice-select").value,
        model_id:         $("model-select").value,
        stability:        parseFloat($("stability-slider").value),
        similarity_boost: parseFloat($("similarity-slider").value),
        style:            parseFloat($("style-slider").value),
        speed:            parseFloat($("speed-slider").value),
        pitch:            parseInt($("pitch-slider").value),
        chapter_index:    state.selectedChapterIndex,
      }),
    });
    const data = await res.json();

    if (!res.ok) {
      showToast(data.error || "Conversion failed.", "error");
      resetConvertBtn();
      return;
    }

    state.currentJobId = data.job_id;
    startPolling(data.job_id);
  } catch (e) {
    showToast("Conversion error: " + e.message, "error");
    resetConvertBtn();
  }
}

function startPolling(jobId) {
  clearInterval(state.pollingInterval);
  state.pollingInterval = setInterval(async () => {
    try {
      const res = await fetch(`/api/job/${jobId}`);
      const job = await res.json();

      updateProgressBar(job.progress || 0, job.message || "Processing...");

      if (job.status === "done") {
        clearInterval(state.pollingInterval);
        resetConvertBtn();
        hideProgress();
        showAudioPlayer(job);
        showToast("🎉 Audio is ready!", "success");
      } else if (job.status === "failed") {
        clearInterval(state.pollingInterval);
        resetConvertBtn();
        hideProgress();
        showToast("❌ " + (job.error || "Conversion failed."), "error");
      }
    } catch (e) {
      console.error("Polling error:", e);
    }
  }, 1500);
}

function resetConvertBtn() {
  $("convert-btn").disabled = false;
  $("convert-btn").innerHTML = "🎙️ Convert to Audio";
}

// ── Progress ───────────────────────────────────────────────────────────────
function showProgress() {
  $("progress-section").classList.add("visible");
  updateProgressBar(5, "Starting...");
}

function hideProgress() {
  $("progress-section").classList.remove("visible");
}

function updateProgressBar(pct, message) {
  $("progress-bar").style.width    = pct + "%";
  $("progress-pct").textContent    = pct + "%";
  $("progress-msg").textContent    = message;
}

// ── Audio Player ────────────────────────────────────────────────────────────
function showAudioPlayer(job) {
  const section    = $("audio-player-section");
  const audioEl    = $("audio-player");
  const audioUrl   = `/api/audio/${job.output_path}`;
  const downloadUrl = `/api/download/${job.output_path}`;

  $("audio-title").textContent    = state.metadata?.title || "Generated Audio";
  $("audio-duration").textContent = job.duration
    ? `Duration: ${formatDuration(job.duration)}`
    : "";

  audioEl.src = audioUrl;
  audioEl.load();

  $("download-btn").onclick   = () => window.open(downloadUrl, "_blank");
  $("copy-link-btn").onclick  = () => {
    navigator.clipboard
      .writeText(window.location.origin + audioUrl)
      .then(() => showToast("Link copied!", "success"));
  };

  section.classList.add("visible");
  section.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function hideAudioPlayer() {
  $("audio-player-section").classList.remove("visible");
}

// ── Utils ──────────────────────────────────────────────────────────────────
function showToast(message, type = "info") {
  const container = $("toast-container");
  const toast     = document.createElement("div");
  toast.className  = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.cssText += "opacity:0;transform:translateX(30px);transition:all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

function formatBytes(bytes) {
  if (bytes < 1024)             return bytes + " B";
  if (bytes < 1024 * 1024)     return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function formatDuration(s) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

function escapeHtml(text) {
  const d = document.createElement("div");
  d.appendChild(document.createTextNode(text || ""));
  return d.innerHTML;
}

// Keep convert btn state in sync
setInterval(() => {
  if (state.apiKeyValid && state.fileId) {
    $("convert-btn").disabled = false;
  }
}, 800);
