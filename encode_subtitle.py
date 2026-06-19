import argparse
import os
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont


DEFAULT_STYLE = (
    "FontName=Heiti TC,"
    "Fontsize=64,"
    "PrimaryColour=&H00FFFFFF,"
    "OutlineColour=&H00000000,"
    "BackColour=&HE0000000,"
    "Bold=-1,"
    "BorderStyle=3,"
    "Outline=5,"
    "Shadow=0,"
    "Alignment=8,"
    "MarginV=120"
)

DEFAULT_FONT_PATHS = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]

IMAGE_FONT_SIZE = 64
IMAGE_STROKE_WIDTH = 5
IMAGE_TEXT_FILL = (255, 255, 255, 255)
IMAGE_STROKE_FILL = (0, 0, 0, 255)
IMAGE_BOX_FILL = (0, 0, 0, 135)
IMAGE_BOX_RADIUS = 10
IMAGE_PADDING_X = 18
IMAGE_PADDING_Y = 8
IMAGE_LINE_SPACING = 4
IMAGE_MAX_WIDTH = 980


def srt_time_to_ass(time_text):
    hours, minutes, rest = time_text.strip().replace(",", ".").split(":")
    seconds, milliseconds = rest.split(".")
    centiseconds = milliseconds[:2].ljust(2, "0")
    return f"{int(hours)}:{minutes}:{seconds}.{centiseconds}"


def srt_time_to_seconds(time_text):
    hours, minutes, rest = time_text.strip().replace(",", ".").split(":")
    seconds, milliseconds = rest.split(".")
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(milliseconds.ljust(3, "0")[:3]) / 1000
    )


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


def parse_srt_image_blocks(srt_text):
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
        text = "\n".join(lines[timing_index + 1:])
        blocks.append(
            (
                srt_time_to_seconds(start_text),
                srt_time_to_seconds(end_text),
                text,
            )
        )

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
    back = ass_color_from_style(style, "BackColour", "&H00000000")
    bold = style_value(style, "Bold", "0")
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
            f"{outline},{back},{bold},0,0,0,100,100,0,0,{border_style},"
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


def load_subtitle_font(font_size=IMAGE_FONT_SIZE):
    for font_path in DEFAULT_FONT_PATHS:
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, font_size)
    return ImageFont.load_default(size=font_size)


def text_width(draw, text, font, stroke_width=IMAGE_STROKE_WIDTH):
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    return bbox[2] - bbox[0]


def wrap_subtitle_line(draw, line, font, max_text_width):
    if text_width(draw, line, font) <= max_text_width:
        return [line]

    wrapped = []
    current = ""
    for char in line:
        candidate = f"{current}{char}"
        if current and text_width(draw, candidate, font) > max_text_width:
            wrapped.append(current)
            current = char
        else:
            current = candidate

    if current:
        wrapped.append(current)

    return wrapped


def wrap_subtitle_text(draw, text, font, max_text_width):
    lines = []
    for line in text.splitlines():
        if line:
            lines.extend(wrap_subtitle_line(draw, line, font, max_text_width))
    return lines


def render_subtitle_overlay(
    text,
    output_path,
    font=None,
    max_width=IMAGE_MAX_WIDTH,
    font_size=IMAGE_FONT_SIZE,
):
    font = font or load_subtitle_font(font_size)
    measure_image = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    measure_draw = ImageDraw.Draw(measure_image)
    max_text_width = max_width - IMAGE_PADDING_X * 2
    lines = wrap_subtitle_text(measure_draw, text, font, max_text_width)

    if not lines:
        lines = [" "]

    line_bboxes = [
        measure_draw.textbbox(
            (0, 0),
            line,
            font=font,
            stroke_width=IMAGE_STROKE_WIDTH,
        )
        for line in lines
    ]
    line_widths = [bbox[2] - bbox[0] for bbox in line_bboxes]
    line_heights = [bbox[3] - bbox[1] for bbox in line_bboxes]
    text_height = sum(line_heights) + IMAGE_LINE_SPACING * (len(lines) - 1)
    image_width = min(max(line_widths) + IMAGE_PADDING_X * 2, max_width)
    image_height = text_height + IMAGE_PADDING_Y * 2

    image = Image.new("RGBA", (image_width, image_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (0, 0, image_width, image_height),
        radius=IMAGE_BOX_RADIUS,
        fill=IMAGE_BOX_FILL,
    )

    y = IMAGE_PADDING_Y
    for line, bbox, line_width, line_height in zip(
        lines, line_bboxes, line_widths, line_heights
    ):
        x = (image_width - line_width) / 2 - bbox[0]
        draw.text(
            (x, y - bbox[1]),
            line,
            font=font,
            fill=IMAGE_TEXT_FILL,
            stroke_width=IMAGE_STROKE_WIDTH,
            stroke_fill=IMAGE_STROKE_FILL,
        )
        y += line_height + IMAGE_LINE_SPACING

    image.save(output_path)
    return output_path


def encode_subtitle_with_ass(
    input_video,
    subtitle,
    output_video,
    style=DEFAULT_STYLE,
    crf=20,
    preset="veryfast",
):
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_subtitle = os.path.join(temp_dir, "subtitle.ass")
        write_positioned_ass(subtitle, temp_subtitle, style=style)

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_video,
            "-vf",
            "subtitles=subtitle.ass",
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

    return result


def encode_subtitle_with_images(
    input_video,
    subtitle,
    output_video,
    crf=20,
    preset="veryfast",
    x="(main_w-overlay_w)/2",
    y=610,
):
    with open(subtitle, "r", encoding="utf-8-sig") as srt_file:
        blocks = parse_srt_image_blocks(srt_file.read())

    if not blocks:
        raise ValueError(f"No subtitle blocks found: {subtitle}")

    with tempfile.TemporaryDirectory() as temp_dir:
        font = load_subtitle_font()
        overlay_paths = []
        for index, (_, _, text) in enumerate(blocks):
            overlay_path = os.path.join(temp_dir, f"subtitle_{index}.png")
            render_subtitle_overlay(text, overlay_path, font=font)
            overlay_paths.append(overlay_path)

        cmd = ["ffmpeg", "-y", "-i", input_video]
        for overlay_path in overlay_paths:
            cmd.extend(["-loop", "1", "-i", overlay_path])

        filter_steps = []
        previous_stream = "[0:v]"
        for index, (start, end, _) in enumerate(blocks):
            output_stream = "[vout]" if index == len(blocks) - 1 else f"[v{index + 1}]"
            enable = f"between(t\\,{start:.3f}\\,{end:.3f})"
            filter_steps.append(
                f"{previous_stream}[{index + 1}:v]"
                f"overlay=x={x}:y={y}:enable='{enable}'{output_stream}"
            )
            previous_stream = output_stream

        cmd.extend(
            [
                "-filter_complex",
                ";".join(filter_steps),
                "-map",
                "[vout]",
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-crf",
                str(crf),
                "-preset",
                preset,
                "-c:a",
                "copy",
                "-shortest",
                output_video,
            ]
        )

        result = subprocess.run(cmd, capture_output=True, text=True)

    return result


def encode_subtitle(
    input_video,
    subtitle,
    output_video,
    style=DEFAULT_STYLE,
    crf=20,
    preset="veryfast",
    renderer="image",
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

    if renderer == "ass":
        result = encode_subtitle_with_ass(
            input_video,
            subtitle,
            output_video,
            style=style,
            crf=crf,
            preset=preset,
        )
    elif renderer == "image":
        result = encode_subtitle_with_images(
            input_video,
            subtitle,
            output_video,
            crf=crf,
            preset=preset,
        )
    else:
        raise ValueError(f"Unknown renderer: {renderer}")

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
    parser.add_argument(
        "--renderer",
        choices=("image", "ass"),
        default="image",
        help="Subtitle renderer. image uses PNG overlays for real alpha.",
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
            renderer=args.renderer,
        )
    except Exception as exc:
        print(exc)
        raise SystemExit(1)

    print(f"Wrote: {output_video}")


if __name__ == "__main__":
    main()
