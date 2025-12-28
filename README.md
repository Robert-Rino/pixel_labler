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

Download videos from YouTube, automatically organizing them into folders with metadata.

### Usage
```bash
uv run yt_download.py "YOUTUBE_URL"
```

### Features
- **Auto-Folder**: Creates a folder named after the video title.
- **Metadata**: Generates `metadata.md` with Source, Title, and Description.
- **Auto-Transcribe Shorts**: If the video is a Short (< 180s), it automatically generates Chinese subtitles (`zh.srt`).
- **Options**:
  - `--root_dir`: Specify base directory for downloads (default: current dir).

---

## 2. Transcription Tool (`transcript.py`)

Generate SRT subtitles using separate transcription (faster-whisper) and translation (Ollama/ArgosTranslate) engines.

### Usage
```bash
uv run transcript.py /path/to/video.mp4
```

### Options
- `--model_size`: Whisper model size (default: `large-v3`).
- `--device`: `cuda` or `cpu` (default: auto).
- `--compute_type`: Quantization type (default: `float16`).
- `--translation_engine`: `ollama` (default) or `argostranslate`.
- `--ollama_model`: Model for Ollama translation (default: `llama3`).
- `--output`: Output filename (default: `zh.srt` in the same folder as input).
- `--no-translate`: Skip translation (output English only).

---

## 3. Batch Clipper (`crop.py`)

Process a long video into multiple clips based on a list defined in a Markdown or CSV file.

### Structure
Ensure your directory looks like this:
```
RootFolder/
├── crop_info.csv (or crop_info.md)  # Clip definitions
├── original.mp4                     # Source video
└── metadata.md (Optional)           # Root metadata to prepend to clips
```

### Input Format (`crop_info.csv`)
Columns: `No, Start, End, Summary, Title, Hook`
Example:
```csv
1, 00:00:10, 00:00:20, Funny moment, My Clip Title, Wait for it!
```

### Usage
```bash
uv run crop.py /path/to/RootFolder
```

### Features
- **Multiple Outputs**: Generates `stacked.mp4` (Vertical), `cam.mp4`, `screen.mp4`, `raw.mp4`, and `audio.wav`.
- **Auto-Transcribe**: Automatically generates `zh.srt` for `raw.mp4`.
- **Metadata Inheritance**: Prepends content from root `metadata.md` to each clip's metadata.
- **Time Padding**: Automatically adds buffer (-5s start, +5s end).
- **Custom Crops**: Use `--cam "w:h:x:y"` and `--screen "w:h:x:y"` to override defaults.

---

## 4. Interactive Crop UI (`main.py`)

A graphical tool to visually determine FFmpeg crop parameters.

### Usage
```bash
uv run main.py
```
Or with arguments:
```bash
uv run main.py --video_path video.mp4 --frame 120
```

### Workflow
1. **Load Video**: Open a video file.
2. **Navigate**: Jump to specific timestamps or frames.
3. **Draw**: Drag to draw rectangles around areas of interest (e.g., Face Cam, Game Screen).
4. **Get Command**: The tool generates the `crop=w:h:x:y` string for you.
