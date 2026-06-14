import argparse
import os
from pathlib import Path

import srt
from flask import Flask, jsonify, request, send_file


ROOT = Path.cwd().resolve()
app = Flask(__name__)
DEFAULT_DIR = None
DEFAULT_VIDEO = "stacked.mp4"
DEFAULT_SRT = "result-zh.srt"


def resolve_workspace_path(path):
    resolved = (ROOT / path).resolve()
    if ROOT != resolved and ROOT not in resolved.parents:
        raise ValueError("Path must stay inside the repository")
    return resolved


def format_srt_time(value):
    total_ms = max(0, round(value.total_seconds() * 1000))
    hours = total_ms // 3_600_000
    total_ms -= hours * 3_600_000
    minutes = total_ms // 60_000
    total_ms -= minutes * 60_000
    seconds = total_ms // 1_000
    total_ms -= seconds * 1_000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{total_ms:03d}"


def subtitle_to_json(subtitle):
    return {
        "index": subtitle.index,
        "start": subtitle.start.total_seconds(),
        "end": subtitle.end.total_seconds(),
        "text": subtitle.content,
    }


def write_srt(subtitles, output_path):
    with open(output_path, "w", encoding="utf-8") as output_file:
        for fallback_index, item in enumerate(subtitles, start=1):
            index = int(item.get("index") or fallback_index)
            start = max(0.0, float(item["start"]))
            end = max(start + 0.001, float(item["end"]))
            text = str(item.get("text") or "").strip()
            output_file.write(f"{index}\n")
            output_file.write(
                f"{seconds_to_srt_time(start)} --> {seconds_to_srt_time(end)}\n"
            )
            output_file.write(f"{text}\n\n")


def seconds_to_srt_time(seconds):
    total_ms = max(0, round(seconds * 1000))
    hours = total_ms // 3_600_000
    total_ms -= hours * 3_600_000
    minutes = total_ms // 60_000
    total_ms -= minutes * 60_000
    seconds = total_ms // 1_000
    total_ms -= seconds * 1_000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{total_ms:03d}"


def load_project_from_request():
    clip_dir = request.args.get("dir") or DEFAULT_DIR
    if not clip_dir:
        raise ValueError("Missing clip dir. Start with --dir or pass ?dir=...")

    video_name = request.args.get("video") or DEFAULT_VIDEO
    srt_name = request.args.get("srt") or DEFAULT_SRT
    clip_path = resolve_workspace_path(clip_dir)
    video_path = resolve_workspace_path(os.path.join(clip_dir, video_name))
    srt_path = resolve_workspace_path(os.path.join(clip_dir, srt_name))

    if not clip_path.is_dir():
        raise FileNotFoundError(f"Clip folder not found: {clip_path}")
    if not video_path.is_file():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if not srt_path.is_file():
        raise FileNotFoundError(f"SRT file not found: {srt_path}")

    return clip_dir, video_name, srt_name, video_path, srt_path


@app.route("/")
def index():
    return HTML


@app.route("/api/project")
def project():
    try:
        clip_dir, video_name, srt_name, video_path, srt_path = load_project_from_request()
        subtitles = list(srt.parse(srt_path.read_text(encoding="utf-8")))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(
        {
            "clipDir": clip_dir,
            "videoName": video_name,
            "srtName": srt_name,
            "videoUrl": f"/media?path={video_path.relative_to(ROOT)}",
            "subtitles": [subtitle_to_json(item) for item in subtitles],
        }
    )


@app.route("/api/save", methods=["POST"])
def save():
    payload = request.get_json(force=True)
    try:
        srt_path = resolve_workspace_path(payload["srtPath"])
        write_srt(payload["subtitles"], srt_path)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"status": "ok", "path": str(srt_path.relative_to(ROOT))})


@app.route("/media")
def media():
    try:
        media_path = resolve_workspace_path(request.args["path"])
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    return send_file(media_path, conditional=True)


HTML = r"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Subtitle Editor</title>
  <style>
    :root {
      --accent: #14b870;
      --accent-soft: rgba(20, 184, 112, 0.16);
      --ink: #171717;
      --muted: #71717a;
      --line: #e5e7eb;
      --panel: #ffffff;
      --wash: #f7f7f8;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      height: 100vh;
      overflow: hidden;
      background: var(--wash);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    button, select, input, textarea {
      font: inherit;
    }

    .app {
      display: grid;
      grid-template-rows: 62px minmax(0, 1fr) 160px;
      height: 100vh;
    }

    .topbar {
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      align-items: center;
      gap: 16px;
      padding: 12px 16px;
      border-bottom: 1px solid var(--line);
      background: #fbfbfc;
    }

    .top-left, .top-center, .top-right {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .top-right { justify-content: flex-end; }

    .back {
      width: 34px;
      height: 34px;
      border: 0;
      border-radius: 17px;
      background: transparent;
      color: #52525b;
      cursor: pointer;
      font-size: 22px;
    }

    .segmented {
      display: flex;
      padding: 3px;
      gap: 2px;
      border-radius: 10px;
      background: #ececef;
    }

    .segmented button {
      min-width: 48px;
      height: 32px;
      border: 0;
      border-radius: 8px;
      background: transparent;
      color: #6b7280;
      cursor: pointer;
    }

    .segmented .active {
      background: var(--accent);
      color: #fff;
      font-weight: 650;
    }

    .ghost-icon {
      width: 36px;
      height: 36px;
      border: 0;
      border-radius: 18px;
      background: transparent;
      color: #9ca3af;
      cursor: pointer;
      font-size: 20px;
    }

    .save-button {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      height: 38px;
      border: 0;
      border-radius: 10px;
      padding: 0 16px;
      background: var(--accent);
      color: #fff;
      font-weight: 700;
      cursor: pointer;
    }

    .workspace {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 392px;
      gap: 20px;
      min-height: 0;
      padding: 8px 14px 10px;
    }

    .transcript-panel, .side-card, .wave-panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
    }

    .transcript-panel {
      overflow: auto;
      padding: 26px 26px 32px;
    }

    .transcript {
      max-width: 100%;
      font-size: 19px;
      line-height: 1.85;
      word-break: break-word;
    }

    .subtitle-token {
      display: inline;
      border-radius: 7px;
      padding: 2px 3px;
      cursor: text;
      outline: 0;
    }

    .subtitle-token:hover {
      background: rgba(0, 0, 0, 0.04);
    }

    .subtitle-token.selected {
      background: var(--accent-soft);
      box-shadow: 0 0 0 2px rgba(20, 184, 112, 0.2);
    }

    .subtitle-token.active {
      color: #06965a;
      font-weight: 700;
    }

    .time {
      color: var(--muted);
      font-size: 14px;
      user-select: none;
      padding: 0 3px;
    }

    .side {
      display: grid;
      grid-template-rows: 220px minmax(0, 1fr);
      gap: 16px;
      min-height: 0;
    }

    .preview-frame {
      position: relative;
      overflow: hidden;
      border-radius: 12px;
      background: #000;
    }

    video {
      width: 100%;
      height: 100%;
      object-fit: contain;
      display: block;
    }

    .subtitle-overlay {
      position: absolute;
      left: 18px;
      right: 18px;
      bottom: 28px;
      text-align: center;
      color: #fff;
      font-size: 24px;
      line-height: 1.25;
      font-weight: 800;
      text-shadow: 0 2px 2px #000, 0 0 8px #000;
      pointer-events: none;
    }

    .side-card {
      display: grid;
      grid-template-rows: 46px minmax(0, 1fr);
      overflow: hidden;
    }

    .tabs {
      display: grid;
      grid-template-columns: 1fr 1fr;
      border-bottom: 1px solid var(--line);
      font-weight: 700;
      font-size: 14px;
      color: #52525b;
    }

    .tab {
      display: flex;
      align-items: center;
      justify-content: center;
      border-bottom: 2px solid transparent;
    }

    .tab.active {
      color: var(--ink);
      border-color: var(--accent);
    }

    .properties {
      padding: 18px;
      min-height: 0;
      overflow: auto;
    }

    .empty-state {
      margin-top: 34px;
      color: #737373;
      text-align: center;
      font-size: 14px;
    }

    .field {
      display: grid;
      gap: 7px;
      margin-bottom: 14px;
    }

    .field label {
      color: #6b7280;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }

    .field input, .field textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 9px 10px;
      outline: 0;
      background: #fff;
    }

    .field textarea {
      min-height: 118px;
      resize: vertical;
      line-height: 1.5;
    }

    .field input:focus, .field textarea:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px var(--accent-soft);
    }

    .danger-button {
      width: 100%;
      height: 38px;
      border: 1px solid #fecaca;
      border-radius: 9px;
      background: #fff7f7;
      color: #b91c1c;
      cursor: pointer;
      font-weight: 700;
    }

    .danger-button:hover {
      background: #fee2e2;
    }

    .wave-panel {
      position: relative;
      margin: 0 14px 10px;
      overflow: hidden;
      display: grid;
      grid-template-rows: 1fr 46px;
    }

    .wave-wrap {
      position: relative;
      min-height: 0;
      cursor: grab;
      touch-action: none;
      background:
        repeating-linear-gradient(to right, transparent 0, transparent calc(6.25% - 1px), #cfd4dc calc(6.25% - 1px), #cfd4dc 6.25%);
    }

    .wave-wrap.dragging {
      cursor: grabbing;
    }

    #waveCanvas {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
    }

    .subtitle-ranges, .playhead-layer, .ticks {
      position: absolute;
      inset: 0;
      pointer-events: none;
    }

    .range {
      position: absolute;
      top: 34px;
      height: 48px;
      min-width: 3px;
      border-radius: 7px;
      background: rgba(20, 184, 112, 0.18);
      border-left: 2px solid rgba(20, 184, 112, 0.7);
      pointer-events: auto;
      cursor: pointer;
    }

    .range.selected {
      background: rgba(20, 184, 112, 0.33);
      border-left-color: var(--accent);
    }

    .playhead {
      position: absolute;
      top: 8px;
      bottom: 8px;
      width: 2px;
      background: #111827;
      transform: translateX(-1px);
    }

    .ticks {
      display: flex;
      justify-content: space-between;
      padding: 7px 15px 0;
      color: #111827;
      font-size: 12px;
    }

    .controls {
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      align-items: center;
      gap: 16px;
      padding: 7px 14px 12px;
      border-top: 1px solid #eef0f3;
    }

    .zoom-tools, .play-tools, .time-tools {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .play-tools { justify-content: center; }
    .time-tools { justify-content: flex-end; }

    .small-button {
      min-width: 34px;
      height: 30px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      color: #52525b;
      cursor: pointer;
    }

    .rate {
      height: 34px;
      min-width: 82px;
      border: 1px solid var(--line);
      border-radius: 9px;
      padding: 0 10px;
      background: #fff;
    }

    .play-button {
      width: 38px;
      height: 38px;
      border: 0;
      border-radius: 19px;
      background: transparent;
      color: #52525b;
      cursor: pointer;
      font-size: 28px;
      line-height: 1;
    }

    .status {
      color: #06965a;
      font-size: 13px;
      min-width: 110px;
      text-align: right;
    }

    .error {
      margin: 24px;
      padding: 16px;
      border: 1px solid #fecaca;
      border-radius: 12px;
      background: #fff1f2;
      color: #9f1239;
    }
  </style>
</head>
<body>
  <div class="app">
    <header class="topbar">
      <div class="top-left">
        <button class="back" title="Back">‹</button>
        <div class="segmented" aria-label="Mode">
          <button class="active">模式</button>
          <button>直式</button>
        </div>
      </div>
      <div class="top-center">
        <button class="ghost-icon" title="Undo">↶</button>
        <button class="ghost-icon" title="Redo">↷</button>
        <button class="ghost-icon" title="Search">⌕</button>
      </div>
      <div class="top-right">
        <span id="status" class="status"></span>
        <button id="saveTop" class="save-button">⇩ 儲存 SRT</button>
      </div>
    </header>

    <main class="workspace" id="workspace">
      <section class="transcript-panel">
        <div id="transcript" class="transcript"></div>
      </section>

      <aside class="side">
        <div class="preview-frame">
          <video id="video" preload="metadata"></video>
          <div id="subtitleOverlay" class="subtitle-overlay"></div>
        </div>
        <section class="side-card">
          <div class="tabs">
            <div class="tab">設定</div>
            <div class="tab active">屬性</div>
          </div>
          <div id="properties" class="properties">
            <div class="empty-state">選擇一個段落以查看屬性</div>
          </div>
        </section>
      </aside>
    </main>

    <section class="wave-panel">
      <div id="waveWrap" class="wave-wrap">
        <canvas id="waveCanvas"></canvas>
        <div id="ranges" class="subtitle-ranges"></div>
        <div class="playhead-layer"><div id="playhead" class="playhead"></div></div>
        <div id="ticks" class="ticks"></div>
      </div>
      <div class="controls">
        <div class="zoom-tools">
          <button id="zoomOut" class="small-button" title="Show more seconds">⌕−</button>
          <span id="zoomLabel" style="color:#6b7280;font-size:13px;">15s</span>
          <button id="zoomIn" class="small-button" title="Show fewer seconds">⌕＋</button>
        </div>
        <div class="play-tools">
          <select id="rate" class="rate">
            <option value="0.5">0.5x</option>
            <option value="0.75">0.75x</option>
            <option value="1" selected>1x</option>
            <option value="1.25">1.25x</option>
            <option value="1.5">1.5x</option>
          </select>
          <button id="play" class="play-button" title="Play/Pause">▷</button>
        </div>
        <div class="time-tools">
          <span style="color:#52525b;">◔</span>
          <span id="clock" style="font-size:13px;"><span style="color:#06965a;">00:00</span> / 00:00</span>
        </div>
      </div>
    </section>
  </div>

  <script>
    const params = new URLSearchParams(location.search);
    const state = {
      subtitles: [],
      selected: null,
      active: null,
      project: null,
      duration: 0,
      viewStart: 0,
      viewDuration: 15,
      audioData: null,
      audioDuration: 0,
      waveDrag: null,
      suppressWaveClick: false,
      composing: false,
      dirty: false,
    };

    const transcriptEl = document.getElementById("transcript");
    const video = document.getElementById("video");
    const overlay = document.getElementById("subtitleOverlay");
    const properties = document.getElementById("properties");
    const playButton = document.getElementById("play");
    const rateSelect = document.getElementById("rate");
    const clock = document.getElementById("clock");
    const saveTop = document.getElementById("saveTop");
    const statusEl = document.getElementById("status");
    const waveWrap = document.getElementById("waveWrap");
    const canvas = document.getElementById("waveCanvas");
    const rangesEl = document.getElementById("ranges");
    const playhead = document.getElementById("playhead");
    const ticksEl = document.getElementById("ticks");
    const zoomOut = document.getElementById("zoomOut");
    const zoomIn = document.getElementById("zoomIn");
    const zoomLabel = document.getElementById("zoomLabel");

    init();

    async function init() {
      try {
        const response = await fetch(`/api/project?${params.toString()}`);
        const project = await response.json();
        if (!response.ok) throw new Error(project.error || "Failed to load project");
        state.project = project;
        state.subtitles = project.subtitles;
        video.src = project.videoUrl;
        renderTranscript();
        renderProperties();
        setStatus(`${project.srtName}`);
      } catch (error) {
        document.body.innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
      }
    }

    function renderTranscript() {
      transcriptEl.innerHTML = "";
      state.subtitles.forEach((item, i) => {
        const time = document.createElement("span");
        time.className = "time";
        time.textContent = `(${formatShortTime(item.start)})`;
        transcriptEl.appendChild(time);

        const span = document.createElement("span");
        span.className = "subtitle-token";
        span.contentEditable = "true";
        span.spellcheck = false;
        span.dataset.index = i;
        span.textContent = item.text;
        span.addEventListener("focus", () => {
          video.pause();
          selectSubtitle(i, true);
        });
        span.addEventListener("click", () => selectSubtitle(i, true));
        span.addEventListener("input", () => updateSubtitleText(i, span.textContent));
        span.addEventListener("compositionstart", () => { state.composing = true; });
        span.addEventListener("compositionend", () => {
          state.composing = false;
          updateSubtitleText(i, span.textContent);
        });
        span.addEventListener("keydown", (event) => {
          if (event.isComposing || state.composing) return;
          if (event.key === "Enter") {
            event.preventDefault();
            span.blur();
          }
        });
        transcriptEl.appendChild(span);
        transcriptEl.appendChild(document.createTextNode(" "));
      });
      updateSelectionClasses();
    }

    function renderProperties() {
      if (state.selected === null) {
        properties.innerHTML = `<div class="empty-state">選擇一個段落以查看屬性</div>`;
        return;
      }

      const item = state.subtitles[state.selected];
      properties.innerHTML = `
        <div class="field">
          <label>Index</label>
          <input id="propIndex" value="${item.index}" disabled>
        </div>
        <div class="field">
          <label>Start</label>
          <input id="propStart" value="${secondsToInput(item.start)}">
        </div>
        <div class="field">
          <label>End</label>
          <input id="propEnd" value="${secondsToInput(item.end)}">
        </div>
        <div class="field">
          <label>Subtitle</label>
          <textarea id="propText">${escapeHtml(item.text)}</textarea>
        </div>
        <button id="deleteSubtitle" class="danger-button">刪除這段字幕</button>
      `;

      document.getElementById("propStart").addEventListener("change", (event) => {
        item.start = inputToSeconds(event.target.value, item.start);
        markDirty();
        renderRanges();
      });
      document.getElementById("propEnd").addEventListener("change", (event) => {
        item.end = inputToSeconds(event.target.value, item.end);
        markDirty();
        renderRanges();
      });
      document.getElementById("propText").addEventListener("input", (event) => {
        updateSubtitleText(state.selected, event.target.value, false);
        const token = transcriptEl.querySelector(`[data-index="${state.selected}"]`);
        if (token) token.textContent = event.target.value;
      });
      document.getElementById("propText").addEventListener("compositionstart", () => {
        state.composing = true;
      });
      document.getElementById("propText").addEventListener("compositionend", (event) => {
        state.composing = false;
        updateSubtitleText(state.selected, event.target.value, false);
        const token = transcriptEl.querySelector(`[data-index="${state.selected}"]`);
        if (token) token.textContent = event.target.value;
      });
      document.getElementById("propText").addEventListener("focus", () => {
        video.pause();
      });
      document.getElementById("propText").addEventListener("keydown", (event) => {
        if (event.isComposing || state.composing) return;
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          event.target.blur();
        }
      });
      document.getElementById("deleteSubtitle").addEventListener("click", () => {
        deleteSelectedSubtitle();
      });
    }

    function updateSubtitleText(index, text, syncProperties = true) {
      state.subtitles[index].text = text.trim();
      markDirty();
      updateOverlay();
      if (syncProperties && state.selected === index) {
        const textarea = document.getElementById("propText");
        if (textarea && textarea.value !== text) textarea.value = text;
      }
    }

    function selectSubtitle(index, seek = false) {
      if (index < 0 || index >= state.subtitles.length) return;
      state.selected = index;
      if (seek) video.currentTime = state.subtitles[index].start;
      ensureTimeVisible(state.subtitles[index].start);
      renderProperties();
      updateSelectionClasses();
      renderRanges();
      updateOverlay();
    }

    function deleteSelectedSubtitle() {
      if (state.selected === null) return;
      const removedIndex = state.selected;
      state.subtitles.splice(removedIndex, 1);
      state.subtitles.forEach((item, index) => { item.index = index + 1; });
      if (state.subtitles.length === 0) {
        state.selected = null;
      } else {
        state.selected = Math.min(removedIndex, state.subtitles.length - 1);
        video.currentTime = state.subtitles[state.selected].start;
      }
      markDirty();
      renderTranscript();
      renderProperties();
      renderRanges();
      updateActiveFromTime(video.currentTime);
    }

    function updateSelectionClasses() {
      document.querySelectorAll(".subtitle-token").forEach((token) => {
        const index = Number(token.dataset.index);
        token.classList.toggle("selected", index === state.selected);
        token.classList.toggle("active", index === state.active);
      });
    }

    video.addEventListener("loadedmetadata", () => {
      state.duration = video.duration || lastSubtitleEnd();
      updateZoomLabel();
      renderTicks();
      renderRanges();
      drawWaveform();
      updateClock();
    });

    video.addEventListener("timeupdate", () => {
      updateActiveFromTime(video.currentTime);
      followPlayhead();
      updatePlayhead();
      updateClock();
    });

    video.addEventListener("play", () => { playButton.textContent = "Ⅱ"; });
    video.addEventListener("pause", () => { playButton.textContent = "▷"; });

    playButton.addEventListener("click", () => {
      if (video.paused) video.play();
      else video.pause();
    });

    document.addEventListener("keydown", (event) => {
      if (isEditingText()) return;

      if (event.code === "Space") {
        event.preventDefault();
        if (video.paused) video.play();
        else video.pause();
      }

      if ((event.key === "Delete" || event.key === "Backspace") && state.selected !== null) {
        event.preventDefault();
        deleteSelectedSubtitle();
      }
    });

    rateSelect.addEventListener("change", () => {
      video.playbackRate = Number(rateSelect.value);
    });

    saveTop.addEventListener("click", saveSrt);

    waveWrap.addEventListener("click", (event) => {
      if (state.suppressWaveClick) {
        state.suppressWaveClick = false;
        return;
      }
      if (event.target.classList.contains("range")) return;
      const rect = waveWrap.getBoundingClientRect();
      const ratio = clamp((event.clientX - rect.left) / rect.width, 0, 1);
      video.currentTime = state.viewStart + ratio * visibleDuration();
    });

    waveWrap.addEventListener("pointerdown", (event) => {
      waveWrap.setPointerCapture(event.pointerId);
      waveWrap.classList.add("dragging");
      state.waveDrag = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startViewStart: state.viewStart,
        moved: false,
      };
    });

    waveWrap.addEventListener("pointermove", (event) => {
      if (!state.waveDrag) return;
      const deltaX = event.clientX - state.waveDrag.startX;
      if (Math.abs(deltaX) < 3) return;
      state.waveDrag.moved = true;
      panWaveFromDrag(deltaX);
    });

    waveWrap.addEventListener("pointerup", (event) => {
      finishWaveDrag(event.pointerId);
    });

    waveWrap.addEventListener("pointercancel", (event) => {
      finishWaveDrag(event.pointerId);
    });

    waveWrap.addEventListener("wheel", (event) => {
      const horizontalDelta = Math.abs(event.deltaX) > Math.abs(event.deltaY)
        ? event.deltaX
        : event.shiftKey
          ? event.deltaY
          : 0;
      if (!horizontalDelta) return;
      event.preventDefault();
      panWaveBySeconds((horizontalDelta / waveWrap.clientWidth) * visibleDuration());
    }, { passive: false });

    zoomIn.addEventListener("click", () => {
      setViewDuration(state.viewDuration / 1.5);
    });

    zoomOut.addEventListener("click", () => {
      setViewDuration(state.viewDuration * 1.5);
    });

    window.addEventListener("resize", () => {
      renderRanges();
      renderTicks();
      drawVisibleWaveform();
      updatePlayhead();
    });

    async function saveSrt() {
      setStatus("儲存中...");
      const response = await fetch("/api/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          srtPath: `${state.project.clipDir}/${state.project.srtName}`,
          subtitles: state.subtitles,
        }),
      });
      const result = await response.json();
      if (!response.ok) {
        setStatus(result.error || "儲存失敗");
        return;
      }
      state.dirty = false;
      setStatus(`已儲存 ${result.path}`);
    }

    function updateActiveFromTime(time) {
      const active = state.subtitles.findIndex((item) => time >= item.start && time <= item.end);
      if (active !== state.active) {
        state.active = active >= 0 ? active : null;
        updateSelectionClasses();
        updateOverlay();
        if (state.active !== null) {
          const token = transcriptEl.querySelector(`[data-index="${state.active}"]`);
          if (token && !isElementInView(token)) token.scrollIntoView({ block: "center", behavior: "smooth" });
        }
      } else {
        updateOverlay();
      }
    }

    function updateOverlay() {
      const item = state.active !== null ? state.subtitles[state.active] : null;
      overlay.textContent = item ? item.text : "";
    }

    function renderRanges() {
      const [viewStart, viewEnd] = visibleWindow();
      const duration = visibleDuration();
      rangesEl.innerHTML = "";
      if (!duration) return;
      state.subtitles.forEach((item, index) => {
        if (item.end < viewStart || item.start > viewEnd) return;
        const left = Math.max(item.start, viewStart) - viewStart;
        const width = Math.min(item.end, viewEnd) - Math.max(item.start, viewStart);
        const range = document.createElement("div");
        range.className = "range";
        range.classList.toggle("selected", index === state.selected);
        range.style.left = `${(left / duration) * 100}%`;
        range.style.width = `${Math.max((width / duration) * 100, 0.25)}%`;
        range.title = item.text;
        range.addEventListener("click", (event) => {
          event.stopPropagation();
          selectSubtitle(index, true);
        });
        rangesEl.appendChild(range);
      });
    }

    function renderTicks() {
      const [viewStart] = visibleWindow();
      const duration = visibleDuration();
      ticksEl.innerHTML = "";
      const count = Math.max(2, Math.min(6, Math.floor(duration / 3) + 1));
      for (let i = 0; i < count; i += 1) {
        const time = viewStart + (duration * i) / (count - 1);
        const tick = document.createElement("span");
        tick.textContent = formatShortTime(time);
        ticksEl.appendChild(tick);
      }
    }

    function updatePlayhead() {
      const [viewStart] = visibleWindow();
      const duration = visibleDuration();
      const ratio = duration ? clamp((video.currentTime - viewStart) / duration, 0, 1) : 0;
      playhead.style.left = `${ratio * 100}%`;
    }

    function updateClock() {
      const current = formatShortTime(video.currentTime || 0);
      const total = formatShortTime(state.duration || lastSubtitleEnd());
      clock.innerHTML = `<span style="color:#06965a;">${current}</span> / ${total}`;
    }

    async function drawWaveform() {
      const rect = waveWrap.getBoundingClientRect();
      const width = Math.max(1, Math.floor(rect.width * devicePixelRatio));
      const height = Math.max(1, Math.floor(rect.height * devicePixelRatio));
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, width, height);

      try {
        const response = await fetch(state.project.videoUrl);
        const arrayBuffer = await response.arrayBuffer();
        const audioContext = new AudioContext();
        const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
        state.audioData = audioBuffer.getChannelData(0);
        state.audioDuration = audioBuffer.duration;
        drawPeaks(ctx, state.audioData, width, height);
        await audioContext.close();
      } catch (error) {
        drawFallbackWave(ctx, width, height);
      }
    }

    function drawVisibleWaveform() {
      const rect = waveWrap.getBoundingClientRect();
      const width = Math.max(1, Math.floor(rect.width * devicePixelRatio));
      const height = Math.max(1, Math.floor(rect.height * devicePixelRatio));
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, width, height);

      if (state.audioData) {
        drawPeaks(ctx, state.audioData, width, height);
      } else {
        drawFallbackWave(ctx, width, height);
      }
    }

    function drawPeaks(ctx, data, width, height) {
      const mid = height * 0.58;
      const amp = height * 0.24;
      const [viewStart, viewEnd] = visibleWindow();
      const audioDuration = state.audioDuration || totalDuration();
      const sampleStart = Math.floor((viewStart / audioDuration) * data.length);
      const sampleEnd = Math.max(
        sampleStart + 1,
        Math.min(data.length, Math.ceil((viewEnd / audioDuration) * data.length))
      );
      const samplesPerPixel = Math.max(1, Math.floor((sampleEnd - sampleStart) / width));
      ctx.strokeStyle = "#a9b3c3";
      ctx.lineWidth = Math.max(1, devicePixelRatio);
      ctx.beginPath();
      for (let x = 0; x < width; x += 2) {
        let peak = 0;
        const start = sampleStart + x * samplesPerPixel;
        const end = Math.min(sampleEnd, start + samplesPerPixel);
        for (let i = start; i < end; i += 1) peak = Math.max(peak, Math.abs(data[i]));
        const y = peak * amp;
        ctx.moveTo(x, mid - y);
        ctx.lineTo(x, mid + y);
      }
      ctx.stroke();
    }

    function drawFallbackWave(ctx, width, height) {
      const mid = height * 0.58;
      const [viewStart] = visibleWindow();
      ctx.strokeStyle = "#a9b3c3";
      ctx.lineWidth = Math.max(1, devicePixelRatio);
      ctx.beginPath();
      for (let x = 0; x < width; x += 5) {
        const shifted = x + viewStart * 80;
        const y = Math.sin(shifted * 0.11) * 11 + Math.sin(shifted * 0.037) * 8;
        ctx.moveTo(x, mid - Math.abs(y));
        ctx.lineTo(x, mid + Math.abs(y));
      }
      ctx.stroke();
    }

    function markDirty() {
      state.dirty = true;
      setStatus("未儲存");
    }

    function setStatus(text) {
      statusEl.textContent = text;
    }

    function lastSubtitleEnd() {
      return state.subtitles.reduce((max, item) => Math.max(max, item.end), 0);
    }

    function totalDuration() {
      return state.duration || lastSubtitleEnd() || 0;
    }

    function visibleDuration() {
      return Math.min(state.viewDuration, totalDuration() || state.viewDuration);
    }

    function visibleWindow() {
      const duration = totalDuration();
      const span = visibleDuration();
      const maxStart = Math.max(0, duration - span);
      state.viewStart = clamp(state.viewStart, 0, maxStart);
      return [state.viewStart, state.viewStart + span];
    }

    function ensureTimeVisible(time) {
      const duration = totalDuration();
      const span = visibleDuration();
      const [viewStart, viewEnd] = visibleWindow();
      if (time < viewStart) {
        state.viewStart = clamp(time - span * 0.1, 0, Math.max(0, duration - span));
      } else if (time > viewEnd) {
        state.viewStart = clamp(time - span * 0.85, 0, Math.max(0, duration - span));
      }
      renderTicks();
      renderRanges();
      drawVisibleWaveform();
      updatePlayhead();
      updateZoomLabel();
    }

    function followPlayhead() {
      const [viewStart, viewEnd] = visibleWindow();
      const time = video.currentTime;
      if (time >= viewStart && time <= viewEnd) return;
      ensureTimeVisible(time);
    }

    function setViewDuration(seconds) {
      const duration = totalDuration() || 15;
      const oldSpan = visibleDuration();
      const center = state.viewStart + oldSpan / 2;
      state.viewDuration = clamp(seconds, 3, Math.max(15, Math.min(120, duration)));
      const newSpan = visibleDuration();
      state.viewStart = clamp(center - newSpan / 2, 0, Math.max(0, duration - newSpan));
      renderTicks();
      renderRanges();
      drawVisibleWaveform();
      updatePlayhead();
      updateZoomLabel();
    }

    function panWaveFromDrag(deltaX) {
      const rect = waveWrap.getBoundingClientRect();
      const secondsDelta = -(deltaX / rect.width) * visibleDuration();
      const nextStart = state.waveDrag.startViewStart + secondsDelta;
      setViewStart(nextStart);
    }

    function panWaveBySeconds(secondsDelta) {
      setViewStart(state.viewStart + secondsDelta);
    }

    function setViewStart(nextStart) {
      const duration = totalDuration();
      const span = visibleDuration();
      state.viewStart = clamp(nextStart, 0, Math.max(0, duration - span));
      renderTicks();
      renderRanges();
      drawVisibleWaveform();
      updatePlayhead();
      updateZoomLabel();
    }

    function finishWaveDrag(pointerId) {
      if (!state.waveDrag || state.waveDrag.pointerId !== pointerId) return;
      if (state.waveDrag.moved) state.suppressWaveClick = true;
      state.waveDrag = null;
      waveWrap.classList.remove("dragging");
    }

    function updateZoomLabel() {
      const span = visibleDuration();
      zoomLabel.textContent = span >= 60 ? `${Math.round(span / 60)}m` : `${Math.round(span)}s`;
    }

    function formatShortTime(seconds) {
      seconds = Math.max(0, Math.floor(seconds));
      const minutes = Math.floor(seconds / 60);
      const secs = seconds % 60;
      return `${minutes}:${String(secs).padStart(2, "0")}`;
    }

    function secondsToInput(seconds) {
      const totalMs = Math.max(0, Math.round(seconds * 1000));
      const minutes = Math.floor(totalMs / 60000);
      const secs = Math.floor((totalMs % 60000) / 1000);
      const ms = totalMs % 1000;
      return `${minutes}:${String(secs).padStart(2, "0")}.${String(ms).padStart(3, "0")}`;
    }

    function inputToSeconds(value, fallback) {
      const match = String(value).trim().match(/^(?:(\d+):)?(\d+)(?:[.,](\d{1,3}))?$/);
      if (!match) return fallback;
      const minutes = Number(match[1] || 0);
      const seconds = Number(match[2] || 0);
      const ms = Number((match[3] || "0").padEnd(3, "0"));
      return minutes * 60 + seconds + ms / 1000;
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function isElementInView(element) {
      const rect = element.getBoundingClientRect();
      return rect.top >= 80 && rect.bottom <= window.innerHeight - 180;
    }

    function isEditingText() {
      const element = document.activeElement;
      if (!element) return false;
      const tag = element.tagName;
      return element.isContentEditable || tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
    }

    function clamp(value, min, max) {
      return Math.min(max, Math.max(min, value));
    }
  </script>
</body>
</html>
"""


def main():
    global DEFAULT_DIR, DEFAULT_VIDEO, DEFAULT_SRT

    parser = argparse.ArgumentParser(description="Local SRT proofreading UI")
    parser.add_argument(
        "--dir",
        default="Twitch_VOD_zackrawrr_2026-06-12T12_01_37/Custom_033545_033817",
        help="Clip folder containing the video and SRT",
    )
    parser.add_argument("--video", default="stacked.mp4", help="Video filename")
    parser.add_argument("--srt", default="result-zh.srt", help="SRT filename")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    parser.add_argument("--port", default=8010, type=int, help="Port to bind")
    args = parser.parse_args()

    DEFAULT_DIR = args.dir
    DEFAULT_VIDEO = args.video
    DEFAULT_SRT = args.srt

    app.run(host=args.host, port=args.port, debug=True)


if __name__ == "__main__":
    main()
