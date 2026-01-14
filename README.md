# Pixel Labler / FFmpeg Crop Tool

A comprehensive toolkit for video processing, clipping, transcribing, downloading, and uploading.

## Prerequisites

- **Python 3.9+**
- **[uv](https://github.com/astral-sh/uv)** (Fast Python package installer and resolver)
- **FFmpeg** (Must be installed and strictly in your system PATH)
- **Ollama** (Optional, for local AI translation)

## Installation

This project uses `uv` for dependency management.

1.  **Install dependencies**:
    ```bash
    uv sync
    ```

---

## 1. Monitor & Auto-Downloader (`monitor.py`)

Automatically monitors a Twitch channel for new VODs and triggers the download pipeline.

### Usage
```bash
# Run manually
uv run monitor.py

# Setup Cron (e.g., check every hour)
0 * * * * cd /path/to/repo && uv run monitor.py >> monitor.log 2>&1
```

### Features
- **Smart Tracking**: Uses `memory.txt` to track the last processed VOD timestamp.
- **Auto-Trigger**: Calls `twitch_download.py` immediately when a new VOD is found.
- **Configurable**: 
    - `--channel_url`: Default `https://www.twitch.tv/zackrawrr`.
    - `--memory_file`: File to store state.

---

## 2. Twitch Downloader (`twitch_download.py`)

Download VODs from Twitch using `yt-dlp` (optimized for archiving).

### Usage
```bash
uv run twitch_download.py "TWITCH_VOD_URL"
```

### Features
- **Optimized Video**: Downloads `480p` (or best ≤ 480p) to `original.mp4` (small size for processing).
- **Direct Audio**: Downloads `Audio Only` stream directly to `audio.mp4` (no re-encoding if possible).
- **High Speed**: Uses 10 concurrent threads for downloading.
- **Auto-Pipeline**:
    1. Downloads Video & Audio.
    2. Transcribes Audio (generating `transcript.srt`).
    3. Splits SRT by hour.
    4. Triggers N8N workflow (`analyze`).

### Options
- `--root_dir`: Base directory.
- `--audio` / `--no-audio`: Toggle audio download.

---

## 3. YouTube Downloader (`yt_download.py`)

Download videos from YouTube.

### Usage
```bash
uv run yt_download.py "YOUTUBE_URL"
```

### Features
- **Auto-Folder**: Creates a folder named after the video title (`safe_title/`).
- **Metadata**: Generates `metadata.md`.
- **Audio Extraction**: Automatically extracts audio to `audio.mp4`.
- **Auto-Transcribe**: Automatically transcribes Shorts (< 180s).

---

## 4. Transcription Tool (`transcript.py`)

Generate SRT subtitles using **AssemblyAI** (default) or **faster-whisper**, with translation support using **Google Translate** (default) or **Ollama**.

### Usage
```bash
uv run transcript.py /path/to/video.mp4 --zh_output "zh.srt"
```

### Features
- **Engines**: 
    - `assemblyai` (Default): Requires `ASSEMBLYAI_API_KEY`.
    - `faster_whisper`: Local, GPU/CPU supported.
- **Translation**:
    - `google` (Default): Uses `deep-translator` (Google Translate).
    - `ollama`: Uses local LLM (e.g., Llama 3).
- **Splitting**: Can split long SRTs into hourly chunks (`--split-by-hour`).

### Options
- `--engine`: `assemblyai` (default) or `faster_whisper`.
- `--translation_engine`: `google` (default) or `ollama`.
- `--zh_output`: Path for translated Chinese SRT.
- `--split-by-hour`: Enable splitting `transcript.srt` into `transcript-chunked/`.

---

## 5. Generic Translator (`translate.py`)

Simple CLI tool to translate text/files using Google Translate.

### Usage
```bash
# Translate text string
uv run translate.py "Hello World" -t zh-TW

# Translate file content
uv run translate.py path/to/file.txt
```

---

## 6. Batch Clipper (`crop.py`)

Process a long video into multiple clips based on a list.

### Usage
```bash
uv run crop.py /path/to/RootFolder
```

### Features
- **Formats**: Generates Vertical Stacked (9:16), Cam, Screen, Raw, and Audio.
- **Watermark**: Adds `@StreamFlash` watermark.
- **Auto-Transcribe/Translate**: Generates `transcript.srt` and `zh.srt` for clips.
- **Input**: Reads `crop_info.csv` (Shorts No, Start, End, Summary, Title, Hook).

---

## 7. Interactive Crop UI (`main.py`)

Visual tool to determine FFmpeg crop parameters.

### Usage
```bash
uv run main.py
```
