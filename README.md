# FFmpeg Crop Tool

A Python desktop application to visually determine FFmpeg crop filter parameters from a video file.

## Prerequisites

- **Python 3.9+**
- **[uv](https://github.com/astral-sh/uv)** (Fast Python package installer and resolver)

## Installation

This project uses `uv` for dependency management.

1.  **Clone the repository** (if applicable) or navigate to the project directory.
2.  **Install dependencies**:
    ```bash
    uv sync
    ```

## Usage

### Basic Usage

Run the application with the default settings:

```bash
uv run main.py
```

### Advanced Usage

You can specify a video file and a starting frame number via command-line arguments:

```bash
uv run main.py --video_path "/path/to/your/video.mp4" --frame 120
```

- `--video_path`: Path to the video file you want to process.
- `--frame`: The specific frame number to extract and display (default is 1).

### How to Use the UI

1.  **Load Video**: If not loaded via command line, click "Open Video" to select a file.
    - **Navigate Frames**: Enter a frame number OR a timestamp (e.g., `00:01:30`, `90s`, or `1234`) and click "Go".
      - Supports `HH:MM:SS`, `MM:SS`, or seconds with `s` suffix.
3.  **Draw Crops**:
    - Click and drag on the image to draw a rectangle.
    - You can draw multiple rectangles to get parameters for multiple crops (e.g., face cam, screen capture).
4.  **Get FFmpeg Parameters**:
    - The bottom text area will update in real-time with the crop filter commands.
    - Format: `crop=w:h:x:y`
    - Example: `crop=1920:1080:0:0`
5.  **Reset**: Click "Reset Crops" to clear all selections.

## Output Format

The tool generates output compatible with FFmpeg's crop filter:

```
crop=out_w:out_h:x:y
```

- `out_w`: Width of the cropped area.
- `out_h`: Height of the cropped area.
- `x`: X coordinate of the top-left corner.
- `y`: Y coordinate of the top-left corner.

## Batch Processing (crop.py)

A script to process multiple clips based on a markdown file.

### Structure
Ensure your directory looks like this:
```
RootFolder/
├── crop_info.md (or crop_info.csv)   (Contains the table of clips. Supports Markdown table or CSV format)
├── original.mp4   (The source video)
```

### Usage
```bash
python crop.py /path/to/RootFolder
```

You can also specify custom crop parameters if they differ from the default:

```bash
python crop.py /path/to/RootFolder --cam "569:416:7:663" --screen "829:904:566:176"
```

The script will:
1. Parse `crop_info.md`.
2. Create subfolders for each clip.
3. Automatically padding time (-5s start, +5s end).
4. Generate 4 video files per clip:
   - `stacked.mp4`: Vertical stack of Cam + Screen.
   - `cam.mp4`: Camera crop.
   - `screen.mp4`: Screen crop.
   - `raw.mp4`: Raw cut from original video.
   - `audio.wav`: Extracted audio.
5. **Auto-Transcribe**: Uses `transcript.py` to generate `zh.srt` from `raw.mp4`.
6. Generate `metadata.md` in each subfolder.
