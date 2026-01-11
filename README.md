# Pixel Labler / FFmpeg Crop Tool

A comprehensive toolkit for video processing, clipping, transcribing, downloading, and uploading.

## Prerequisites

- **Python 3.9+**
- **[uv](https://github.com/astral-sh/uv)** (Fast Python package installer and resolver)
- **FFmpeg** (Must be installed and strictly in your system PATH)

## Installation

This project uses `uv` for dependency management.

1.  **Install dependencies**:
    ```bash
    uv sync
    ```

---

## 1. YouTube Downloader (`yt_download.py`)

Download videos from YouTube.

### Usage
```bash
uv run yt_download.py "YOUTUBE_URL"
```

### Features
- **Auto-Folder**: Creates a folder named after the video title (`safe_title/`).
- **Metadata**: Generates `metadata.md`.
- **Audio Extraction**: Automatically extracts audio to `audio.mp4` by default.
- **Auto-Transcribe**:
  - Automatically transcribes Shorts (< 180s) to `transcript.srt` (original) and `zh.srt` (Chinese).
  - Use `--transcript` to force transcription for longer videos.

### Options
- `--root_dir`: Specify base directory for downloads.
- `--transcript`: Force generate transcript (and force audio extraction).
- `--audio` / `--no-audio`: Enable/Disable audio stream extraction (Default: Enabled).

---

## 2. Twitch Downloader (`twitch_download.py`)

Download VODs from Twitch using `twitch-dl`.

### Usage
```bash
uv run twitch_download.py "TWITCH_VOD_URL"
```

### Features
- **High Quality**: Downloads `source` quality by default.
- **Audio Only**: Can optionally download an audio-only track.
- **Metadata**: Extracts JSON metadata to `metadata.md`.
- **Auto-Transcribe**: Automatically transcribes videos < 180s.

### Options
- `--root_dir`: Base directory.
- `--audio`: Also download the audio-only track as `audio.mp4`.

---

## 3. Transcription Tool (`transcript.py`)

Generate SRT subtitles using `faster-whisper`.

### Usage
```bash
uv run transcript.py /path/to/video.mp4 --zh_output "zh.srt"
```

### Features
- **Original Transcript**: ALWAYS generates `transcript.srt` (original language) in the file's directory.
- **Translation**: Optionally translates to Traditional Chinese (Taiwan style) if `--zh_output` is provided.

### Options
- `--zh_output`: Path to save the translated Chinese SRT file (e.g., `zh.srt`). If omitted, only `transcript.srt` is created.
- `--model_size`: Whisper model size (default: `medium`).
- `--device`: `cuda` or `cpu` (default: auto).
- `--translation_engine`: `ollama` (default) or `argostranslate`.
- `--ollama_model`: Ollama model tag (default: `hf.co/chienweichang/Llama-3-Taiwan-8B-Instruct-GGUF`).

---

## 4. Batch Clipper (`crop.py`)

Process a long video into multiple clips based on a list.

### Usage
```bash
uv run crop.py /path/to/RootFolder
```

### Features
- **Multiple Outputs**: Vertical stacked, cam-only, screen-only, raw clip, and audio.
- **Auto-Transcribe**: Automatically generates `transcript.srt` and translated `zh.srt` for `raw.mp4`.
- **Metadata**: Inherits root metadata.

### Input Format (`crop_info.csv`)
Columns: `No, Start, End, Summary, Title, Hook`
```csv
1, 00:00:10, 00:00:20, Summary, Clip Title, Hook text
```

---

## 5. Interactive Crop UI (`main.py`)

A graphical tool to visually determine FFmpeg crop parameters.

### Usage
```bash
uv run main.py
```
