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
2.  **Navigate Frames**: Enter a frame number in the "Frame" box and click "Go" to jump to a specific frame.
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
