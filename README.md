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

Download VODs from Twitch using `yt-dlp` and `chat_utils`.

### Usage
```bash
# Download entire VOD
uv run twitch_download.py "TWITCH_VOD_URL"

# Download specific range (e.g., from minute 10 to 30)
uv run twitch_download.py "TWITCH_VOD_URL" --start_min 10 --duration_min 20
```

### Features
- **Optimized Video**: Downloads `480p` (or best ≤ 480p) to `original.mp4`.
- **Slicing Support**: Can download specific time ranges without fetching the entire VOD.
- **Chat Download**: Automatically fetches full (or sliced) Twitch chat logs using the GQL API.
- **Direct Audio**: Extracts audio directly to `audio.mp4`.
- **Auto-Pipeline**:
    1. Downloads Video, Audio, and Chat.
    2. Transcribes Audio (generating `transcript.srt`).
    3. Triggers N8N workflow (`analyze`).

### Options
- `--root_dir`: Base directory for downloads.
- `--audio` / `--no-audio`: Toggle audio extraction.
- `--start_min`: Start time in minutes.
- `--duration_min`: Duration to download in minutes.

### Python Interface (`downloader.py`)
```bash
# Download an entire Twitch VOD
uv run python -c 'from downloader import TwitchDownloader; TwitchDownloader(root_dir=".").download("TWITCH_VOD_URL")'

# Download a Twitch range/chunk in minutes
uv run python -c 'from downloader import TwitchDownloader; TwitchDownloader(root_dir=".").download("TWITCH_VOD_URL", start_min=0, duration_min=60)'

# Auto-select the correct downloader by URL
uv run python -c 'from downloader import get_downloader; url = "TWITCH_VOD_URL"; get_downloader(url, root_dir=".").download(url)'
```

---

## 3. Chat Downloader (`chat_utils.py`)

A robust Twitch chat downloader using the modern GQL API.

### Usage
```bash
# Download entire chat
uv run python chat_utils.py "TWITCH_VOD_URL" chat.json

# Download specific range (e.g., first hour)
uv run python chat_utils.py "TWITCH_VOD_URL" chat.json 0 60
```

### Features
- **GQL Powered**: Uses Twitch's internal GraphQL API for high reliability.
- **Range Support**: Can jump to any timestamp using `--start_min` and `--duration_min`.
- **Format Compatible**: Produces a structured JSON chat log.

---

## 4. YouTube Downloader (`yt_download.py`)

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

### Python Interface (`downloader.py`)
```bash
# Download a YouTube video
uv run python -c 'from downloader import YTDownloader; YTDownloader(root_dir=".").download("YOUTUBE_URL")'

# Force transcript generation and skip audio extraction
uv run python -c 'from downloader import YTDownloader; YTDownloader(root_dir=".").download("YOUTUBE_URL", force_transcript=True, extract_audio=False)'

# Auto-select the correct downloader by URL
uv run python -c 'from downloader import get_downloader; url = "YOUTUBE_URL"; get_downloader(url, root_dir=".").download(url)'
```

---

## 5. YouTube Uploader (`yt_upload.py`)

Upload a video to YouTube with a title, optional thumbnail, and optional scheduled publish time.

### Usage
```bash
uv run yt_upload.py /path/to/video.mp4 --title "My Video" --thumbnail /path/to/thumb.jpg --publish_time "2026-06-20T15:00:00Z"
```

### Notes
- Uses the YouTube Data API OAuth flow.
- Store your OAuth client secrets in `client_secret.json` or pass `--client_secrets`.
- OAuth tokens are cached in `youtube_token.json` by default.
- `--publish_time` expects ISO-8601 and schedules the upload as private.

---

## 6. Transcription Tool (`transcript.py`)

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

## 7. Generic Translator (`translate.py`)

Simple CLI tool to translate text/files using Google Translate.

### Usage
```bash
# Translate text string
uv run translate.py "Hello World" -t zh-TW

# Translate file content
uv run translate.py path/to/file.txt
```

---

## 8. Batch Clipper (`crop.py`)

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

## 9. Subtitle Encoder (`encode_subtitle.py`)

Burn an SRT subtitle file into a video using FFmpeg/libass.

### Usage
```bash
uv run encode_subtitle.py input.mp4 subtitle.srt output.mp4
```

### Example
```bash
uv run encode_subtitle.py \
  Twitch_VOD_zackrawrr_2026-06-12T12_01_37/Custom_005647_005715/stacked.mp4 \
  Twitch_VOD_zackrawrr_2026-06-12T12_01_37/臘腸-逐字飽.srt \
  Twitch_VOD_zackrawrr_2026-06-12T12_01_37/Custom_005647_005715/result.mp4
```

### Features
- Converts SRT to a temporary ASS subtitle file for stable positioning.
- Burns subtitles into the video stream with `libx264`.
- Copies the original audio stream without re-encoding.
- Default style is black text with white outline.
- Default fixed subtitle anchor is `pos(540,610)` for 1080x1920 stacked videos.

### Options
- `--style`: Override the ASS style string.
- `--crf`: x264 quality value (default: `20`).
- `--preset`: x264 encoding preset (default: `veryfast`).

---

## 10. Interactive Crop UI (`main.py`)

Visual tool to determine FFmpeg crop parameters.

### Usage
```bash
uv run main.py
```
