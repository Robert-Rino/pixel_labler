# Local Whisper Transcription Tool

A local Python tool to transcribe videos (MP4/MOV) to Traditional Chinese SRT subtitles using `faster-whisper`.

## Features
- **Local Processing**: Uses `faster-whisper` (runs on CPU or GPU).
- **Auto Translation**:
    - **English Video**: Translates to Traditional Chinese using either:
        1. **Ollama API** (default, requires local Ollama server).
        2. **ArgosTranslate** (offline, requires model download).
    - **Chinese Video**: Transcribes directly to Traditional Chinese.

## Installation

1.  **Install Dependencies**:
    ```bash
    uv add faster-whisper requests
    ```
2.  **Setup Ollama**:
    - Install [Ollama](https://ollama.com/)
    - Pull the translation model:
      ```bash
      ollama pull llama3
      ```
    - Start the server:
      ```bash
      ollama serve
      ```

## Usage

### Basic Usage
Process a video file. It will auto-detect language and device.

```bash
uv run transcript.py video.mp4
```

### Advanced Options

```bash
uv run transcript.py video.mp4 --model_size large-v3 --device cuda --translate_to_zh True --translation_engine ollama --ollama_model llama3
```

- `--model_size`: `tiny`, `base`, `small`, `medium` (default), `large-v3`.
- `--device`: `auto` (default), `cuda`, `cpu`.
- `--translation_engine`: `ollama` (default) or `argostranslate`.
- `--ollama_model`: Model to use for translation (default: `llama3`). Ensure you have pulled this model.
- `--output`: Output filename (default: `zh.srt`).

### Output
The tool generates a `.srt` file. 
- **Default**: Saves as `zh.srt` **in the same folder as the input video**.
- **Custom**: Use `--output` to specify a filename (saved in video folder) or an absolute path.
