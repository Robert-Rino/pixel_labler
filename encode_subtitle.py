import argparse
import os
import subprocess
import tempfile


DEFAULT_STYLE = (
    "FontName=Heiti TC,"
    "Fontsize=64,"
    "PrimaryColour=&H00000000,"
    "OutlineColour=&H00FFFFFF,"
    "BorderStyle=1,"
    "Outline=6,"
    "Shadow=0,"
    "Alignment=8,"
    "MarginV=120"
)


def srt_time_to_ass(time_text):
    hours, minutes, rest = time_text.strip().replace(",", ".").split(":")
    seconds, milliseconds = rest.split(".")
    centiseconds = milliseconds[:2].ljust(2, "0")
    return f"{int(hours)}:{minutes}:{seconds}.{centiseconds}"


def parse_srt_blocks(srt_text):
    blocks = []
    normalized = srt_text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")

    for block in normalized.strip().split("\n\n"):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if len(lines) < 3:
            continue

        timing_index = 1 if lines[0].isdigit() else 0
        if timing_index >= len(lines) or "-->" not in lines[timing_index]:
            continue

        start_text, end_text = lines[timing_index].split("-->", 1)
        text = r"\N".join(
            line.replace("{", r"\{").replace("}", r"\}")
            for line in lines[timing_index + 1:]
        )
        blocks.append((srt_time_to_ass(start_text), srt_time_to_ass(end_text), text))

    return blocks


def ass_color_from_style(style, key, default):
    for item in style.split(","):
        if item.startswith(f"{key}="):
            return item.split("=", 1)[1]
    return default


def style_value(style, key, default):
    for item in style.split(","):
        if item.startswith(f"{key}="):
            return item.split("=", 1)[1]
    return default


def write_positioned_ass(
    srt_path,
    ass_path,
    style=DEFAULT_STYLE,
    width=1080,
    height=1920,
    x=540,
    y=610,
):
    with open(srt_path, "r", encoding="utf-8-sig") as srt_file:
        blocks = parse_srt_blocks(srt_file.read())

    font_name = style_value(style, "FontName", "Helvetica")
    font_size = style_value(style, "Fontsize", "64")
    primary = ass_color_from_style(style, "PrimaryColour", "&H00000000")
    outline = ass_color_from_style(style, "OutlineColour", "&H00FFFFFF")
    border_style = style_value(style, "BorderStyle", "1")
    outline_size = style_value(style, "Outline", "6")
    shadow = style_value(style, "Shadow", "0")
    alignment = style_value(style, "Alignment", "8")

    with open(ass_path, "w", encoding="utf-8") as ass_file:
        ass_file.write("[Script Info]\n")
        ass_file.write("ScriptType: v4.00+\n")
        ass_file.write(f"PlayResX: {width}\n")
        ass_file.write(f"PlayResY: {height}\n")
        ass_file.write("WrapStyle: 2\n")
        ass_file.write("ScaledBorderAndShadow: yes\n\n")

        ass_file.write("[V4+ Styles]\n")
        ass_file.write(
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        )
        ass_file.write(
            f"Style: Default,{font_name},{font_size},{primary},&H000000FF,"
            f"{outline},&H00000000,0,0,0,0,100,100,0,0,{border_style},"
            f"{outline_size},{shadow},{alignment},0,0,0,1\n\n"
        )

        ass_file.write("[Events]\n")
        ass_file.write(
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text\n"
        )
        for start, end, text in blocks:
            ass_file.write(
                f"Dialogue: 0,{start},{end},Default,,0,0,0,,"
                f"{{\\an8\\pos({x},{y})}}{text}\n"
            )


def encode_subtitle(
    input_video,
    subtitle,
    output_video,
    style=DEFAULT_STYLE,
    crf=20,
    preset="veryfast",
):
    input_video = os.path.abspath(input_video)
    subtitle = os.path.abspath(subtitle)
    output_video = os.path.abspath(output_video)

    if not os.path.exists(input_video):
        raise FileNotFoundError(f"Input video not found: {input_video}")
    if not os.path.exists(subtitle):
        raise FileNotFoundError(f"Subtitle file not found: {subtitle}")

    output_dir = os.path.dirname(output_video)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_subtitle = os.path.join(temp_dir, "subtitle.ass")
        write_positioned_ass(subtitle, temp_subtitle, style=style)

        subtitle_filter = "subtitles=subtitle.ass"
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_video,
            "-vf",
            subtitle_filter,
            "-c:v",
            "libx264",
            "-crf",
            str(crf),
            "-preset",
            preset,
            "-c:a",
            "copy",
            output_video,
        ]

        result = subprocess.run(
            cmd,
            cwd=temp_dir,
            capture_output=True,
            text=True,
        )

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed:\n{result.stderr}")

    return output_video


def main():
    parser = argparse.ArgumentParser(
        description="Burn an SRT subtitle file into a video with FFmpeg."
    )
    parser.add_argument("input_video", help="Path to input video")
    parser.add_argument("subtitle", help="Path to SRT subtitle file")
    parser.add_argument("output_video", help="Path to output video")
    parser.add_argument(
        "--style",
        default=DEFAULT_STYLE,
        help="ASS force_style string for FFmpeg subtitles filter",
    )
    parser.add_argument("--crf", type=int, default=20, help="x264 CRF value")
    parser.add_argument(
        "--preset",
        default="veryfast",
        help="x264 preset, e.g. veryfast, medium, slow",
    )

    args = parser.parse_args()

    try:
        output_video = encode_subtitle(
            args.input_video,
            args.subtitle,
            args.output_video,
            style=args.style,
            crf=args.crf,
            preset=args.preset,
        )
    except Exception as exc:
        print(exc)
        raise SystemExit(1)

    print(f"Wrote: {output_video}")


if __name__ == "__main__":
    main()
