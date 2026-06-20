import argparse
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


POSITIONS = ("top", "middle", "down")
DEFAULT_SIZE = (1280, 720)
RED = (255, 0, 0)
WHITE = (255, 255, 255)
DEFAULT_MARGIN = 32
DEFAULT_PADDING = 16
DEFAULT_FONT_SCALE = 0.07
DEFAULT_RADIUS = 8
DEFAULT_SECOND_FONT_SCALE = 0.06
DEFAULT_EMOJI_SCALE = 0.1
DEFAULT_LAYER_GAP = 4
MIDDLE_Y_OFFSET = -60
SECOND_TITLE_STROKE = (214, 93, 255)
TITLE_BOLD_DIVISOR = 32
TITLE_BOLD_OPACITY = 186


def parse_size(value):
    try:
        width_text, height_text = value.lower().split("x", 1)
        width = int(width_text)
        height = int(height_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("size must look like 1280x720") from exc

    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("size dimensions must be positive")
    return width, height


def _sample_indices(frame_count, sample_count):
    if frame_count <= 0:
        return []

    start = int(frame_count * 0.08)
    end = max(start + 1, int(frame_count * 0.92))
    count = min(sample_count, max(1, end - start))
    return np.linspace(start, end - 1, count, dtype=int).tolist()


def _frame_features(frame):
    small = cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [24, 16], [0, 180, 0, 256])
    hist = cv2.normalize(hist, hist).flatten()
    brightness = float(gray.mean())
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    return hist, brightness, sharpness


def capture_representative_frame(video_path, sample_count=48):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {video_path}")

    try:
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        indices = _sample_indices(frame_count, sample_count)
        if not indices:
            indices = [0]

        candidates = []
        for frame_index in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue

            hist, brightness, sharpness = _frame_features(frame)
            candidates.append(
                {
                    "frame": frame.copy(),
                    "hist": hist,
                    "brightness": brightness,
                    "sharpness": sharpness,
                }
            )

        if not candidates:
            raise ValueError(f"No frames could be read from video: {video_path}")

        mean_hist = np.mean([candidate["hist"] for candidate in candidates], axis=0)
        best = min(candidates, key=lambda candidate: _candidate_score(candidate, mean_hist))
        return best["frame"]
    finally:
        cap.release()


def _candidate_score(candidate, mean_hist):
    hist_distance = cv2.compareHist(
        candidate["hist"].astype("float32"),
        mean_hist.astype("float32"),
        cv2.HISTCMP_BHATTACHARYYA,
    )
    brightness = candidate["brightness"]
    sharpness = candidate["sharpness"]

    brightness_penalty = 0.0
    if brightness < 35:
        brightness_penalty = (35 - brightness) / 35
    elif brightness > 230:
        brightness_penalty = (brightness - 230) / 25

    sharpness_penalty = max(0.0, 45 - sharpness) / 45
    return hist_distance + brightness_penalty + sharpness_penalty


def parse_margin(value):
    try:
        margin = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("margin must be an integer") from exc

    if margin < 0:
        raise argparse.ArgumentTypeError("margin must be zero or greater")
    return margin


def parse_padding(value):
    try:
        padding = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("padding must be an integer") from exc

    if padding < 0:
        raise argparse.ArgumentTypeError("padding must be zero or greater")
    return padding


def parse_font_scale(value):
    try:
        font_scale = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("font scale must be a number") from exc

    if font_scale <= 0:
        raise argparse.ArgumentTypeError("font scale must be positive")
    return font_scale


def parse_radius(value):
    try:
        radius = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("radius must be an integer") from exc

    if radius < 0:
        raise argparse.ArgumentTypeError("radius must be zero or greater")
    return radius


def _fit_resize(image, max_size):
    target_width, target_height = max_size
    source_width, source_height = image.size
    scale = min(target_width / source_width, target_height / source_height)
    resized_size = (round(source_width * scale), round(source_height * scale))
    return image.resize(resized_size, Image.Resampling.LANCZOS)


def _font_candidates():
    return [
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]


def _emoji_font_candidates():
    return [
        "/System/Library/Fonts/Apple Color Emoji.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]


def _load_bold_font(size):
    for font_path in _font_candidates():
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size=size)
            except OSError:
                pass
    return ImageFont.load_default(size=size)


def _load_emoji_font(size):
    for font_path in _emoji_font_candidates():
        if os.path.exists(font_path):
            sizes = [size]
            if os.path.basename(font_path) == "Apple Color Emoji.ttc":
                sizes = sorted(
                    {size, 20, 32, 40, 48, 64, 96, 160},
                    key=lambda candidate: abs(candidate - size),
                )

            for candidate_size in sizes:
                try:
                    return ImageFont.truetype(font_path, size=candidate_size)
                except OSError:
                    pass
    return ImageFont.load_default(size=size)


def _text_size(draw, text, font, stroke_width=None):
    if stroke_width is None:
        stroke_width = max(2, font.size // 18)

    left, top, right, bottom = draw.multiline_textbbox(
        (0, 0),
        text,
        font=font,
        spacing=max(6, font.size // 8),
        stroke_width=stroke_width,
    )
    return right - left, bottom - top


def _wrap_title(title, draw, font, max_width):
    words = title.split()
    if not words:
        return ""

    lines = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        width, _ = _text_size(draw, candidate, font)
        if width <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)
    return "\n".join(lines)


def _fit_title(title, draw, image_size, margin, padding, font_scale=DEFAULT_FONT_SCALE):
    max_width = max(1, image_size[0] - (margin + padding) * 2)
    max_height = max(1, int(image_size[1] * 0.3))
    font_size = max(24, int(image_size[1] * font_scale))

    while font_size >= 18:
        font = _load_bold_font(font_size)
        wrapped = _wrap_title(title, draw, font, max_width)
        width, height = _text_size(draw, wrapped, font)
        if width <= max_width and height <= max_height:
            return font, wrapped
        font_size -= 4

    font = _load_bold_font(18)
    return font, _wrap_title(title, draw, font, max_width)


def title_box(image_size, text_size, position, margin=DEFAULT_MARGIN, padding=DEFAULT_PADDING):
    if position not in POSITIONS:
        raise ValueError(f"position must be one of: {', '.join(POSITIONS)}")

    width, height = image_size
    margin = min(margin, max(0, (min(width, height) - 1) // 2))
    text_width, text_height = text_size
    box_width = min(max(1, width - margin * 2), text_width + padding * 2)
    box_height = min(max(1, height - margin * 2), text_height + padding * 2)
    x = (width - box_width) // 2

    if position == "top":
        y = margin
    elif position == "middle":
        y = (height - box_height) // 2
    else:
        y = height - box_height - margin
    return x, y, x + box_width, y + box_height


def _fit_aux_text(text, draw, image_size, margin, font_scale, single_line=False):
    max_width = max(1, image_size[0] - margin * 2)
    max_height = max(1, int(image_size[1] * 0.22))
    font_size = max(18, int(image_size[1] * font_scale))

    while font_size >= 16:
        font = _load_bold_font(font_size)
        wrapped = text if single_line else _wrap_title(text, draw, font, max_width)
        width, height = _text_size(draw, wrapped, font)
        if width <= max_width and height <= max_height:
            return font, wrapped
        font_size -= 4

    font = _load_bold_font(16)
    return font, _wrap_title(text, draw, font, max_width)


def _fit_emoji(emoji, draw, image_size, font_scale):
    font_size = max(20, int(image_size[1] * font_scale))

    while font_size >= 18:
        font = _load_emoji_font(font_size)
        width, height = _text_size(draw, emoji, font, stroke_width=0)
        if width <= image_size[0] * 0.8 and height <= image_size[1] * 0.18:
            return font
        font_size -= 4

    return _load_emoji_font(18)


def _group_start_y(image_height, group_height, position, margin):
    if position == "top":
        return margin
    if position == "middle":
        return (image_height - group_height) // 2 + MIDDLE_Y_OFFSET
    return image_height - group_height - margin


def _draw_bold_multiline_text(
    draw,
    position,
    text,
    font,
    fill,
    stroke_width=0,
    stroke_fill=None,
    bold_width=1,
    bold_opacity=255,
):
    x, y = position
    offsets = []
    for offset in range(1, bold_width + 1):
        offsets.extend([(offset, 0), (-offset, 0), (0, offset), (0, -offset)])

    for offset_x, offset_y in offsets:
        offset_fill = (*fill, bold_opacity) if len(fill) == 3 else fill
        draw.multiline_text(
            (x + offset_x, y + offset_y),
            text,
            font=font,
            fill=offset_fill,
            anchor=None,
            align="center",
            spacing=max(6, font.size // 8),
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )

    draw.multiline_text(
        (x, y),
        text,
        font=font,
        fill=fill,
        anchor=None,
        align="center",
        spacing=max(6, font.size // 8),
        stroke_width=stroke_width,
        stroke_fill=stroke_fill,
    )


def _title_bold_width(font_size):
    return max(1, font_size // TITLE_BOLD_DIVISOR)


def create_thumbnail(
    frame,
    title,
    output_path,
    position="middle",
    size=DEFAULT_SIZE,
    margin=DEFAULT_MARGIN,
    padding=DEFAULT_PADDING,
    font_scale=DEFAULT_FONT_SCALE,
    radius=DEFAULT_RADIUS,
    second_title=None,
    emoji=None,
    second_font_scale=DEFAULT_SECOND_FONT_SCALE,
    emoji_scale=DEFAULT_EMOJI_SCALE,
):
    if position not in POSITIONS:
        raise ValueError(f"position must be one of: {', '.join(POSITIONS)}")

    output_dir = os.path.dirname(os.path.abspath(output_path))
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(rgb_frame)
    image = _fit_resize(image, size)

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font, wrapped_title = _fit_title(title, draw, image.size, margin, padding, font_scale=font_scale)
    text_width, text_height = _text_size(draw, wrapped_title, font)
    title_box_width = min(max(1, image.width - margin * 2), text_width + padding * 2)
    title_box_height = min(max(1, image.height - margin * 2), text_height + padding * 2)

    emoji_font = None
    emoji_width = 0
    emoji_height = 0
    if emoji:
        emoji_font = _fit_emoji(emoji, draw, image.size, emoji_scale)
        emoji_width, emoji_height = _text_size(draw, emoji, emoji_font, stroke_width=0)

    second_font = None
    wrapped_second_title = ""
    second_width = 0
    second_height = 0
    second_stroke_width = 0
    if second_title:
        second_font, wrapped_second_title = _fit_aux_text(
            second_title,
            draw,
            image.size,
            margin,
            second_font_scale,
            single_line=True,
        )
        second_stroke_width = max(3, second_font.size // 12)
        second_width, second_height = _text_size(
            draw,
            wrapped_second_title,
            second_font,
            stroke_width=second_stroke_width,
        )

    group_height = title_box_height
    if emoji:
        group_height += emoji_height + DEFAULT_LAYER_GAP
    if second_title:
        group_height += second_height + DEFAULT_LAYER_GAP

    group_y = _group_start_y(image.height, group_height, position, margin)
    group_y = max(margin, min(group_y, image.height - margin - group_height))

    current_y = group_y
    if emoji and emoji_font:
        emoji_x = (image.width - emoji_width) // 2
        draw.text(
            (emoji_x, current_y),
            emoji,
            font=emoji_font,
            fill=WHITE,
            embedded_color=True,
        )
        current_y += emoji_height + DEFAULT_LAYER_GAP

    box_left = (image.width - title_box_width) // 2
    box = (box_left, current_y, box_left + title_box_width, current_y + title_box_height)
    draw.rounded_rectangle(box, radius=radius, fill=(*RED, 255))

    text_x = box[0] + (box[2] - box[0] - text_width) // 2
    text_y = box[1] + (box[3] - box[1] - text_height) // 2
    title_bold_width = _title_bold_width(font.size)
    _draw_bold_multiline_text(
        draw,
        (text_x, text_y),
        wrapped_title,
        font,
        WHITE,
        stroke_width=0,
        bold_width=title_bold_width,
        bold_opacity=TITLE_BOLD_OPACITY,
    )
    current_y = box[3] + DEFAULT_LAYER_GAP

    if second_title and second_font:
        second_x = (image.width - second_width) // 2
        second_bold_width = max(1, second_font.size // 36)
        _draw_bold_multiline_text(
            draw,
            (second_x, current_y),
            wrapped_second_title,
            second_font,
            WHITE,
            stroke_width=second_stroke_width,
            stroke_fill=SECOND_TITLE_STROKE,
            bold_width=second_bold_width,
        )

    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    image.save(output_path, quality=95)
    return output_path


def generate_thumbnail(
    video_path,
    title,
    output_path="thumbnail.jpg",
    position="middle",
    size=DEFAULT_SIZE,
    margin=DEFAULT_MARGIN,
    padding=DEFAULT_PADDING,
    font_scale=DEFAULT_FONT_SCALE,
    radius=DEFAULT_RADIUS,
    second_title=None,
    emoji=None,
    second_font_scale=DEFAULT_SECOND_FONT_SCALE,
    emoji_scale=DEFAULT_EMOJI_SCALE,
):
    frame = capture_representative_frame(video_path)
    return create_thumbnail(
        frame,
        title,
        output_path,
        position=position,
        size=size,
        margin=margin,
        padding=padding,
        font_scale=font_scale,
        radius=radius,
        second_title=second_title,
        emoji=emoji,
        second_font_scale=second_font_scale,
        emoji_scale=emoji_scale,
    )


def main():
    parser = argparse.ArgumentParser(description="Generate a video thumbnail with a red title banner.")
    parser.add_argument("video", help="Input video file")
    parser.add_argument("title", help="Title text to draw on the thumbnail")
    parser.add_argument("-o", "--output", default="thumbnail.jpg", help="Output image path")
    parser.add_argument(
        "--position",
        choices=POSITIONS,
        default="middle",
        help="Title banner position: top, middle, or down (default: middle)",
    )
    parser.add_argument("--size", type=parse_size, default=DEFAULT_SIZE, help="Output size, for example 1280x720")
    parser.add_argument(
        "--margin",
        type=parse_margin,
        default=DEFAULT_MARGIN,
        help="Distance in pixels from the image edge for top/down title positions",
    )
    parser.add_argument(
        "--padding",
        type=parse_padding,
        default=DEFAULT_PADDING,
        help="Pixels between the title text and red background edge",
    )
    parser.add_argument(
        "--font-scale",
        type=parse_font_scale,
        default=DEFAULT_FONT_SCALE,
        help="Title font size as a fraction of image height (default: 0.07)",
    )
    parser.add_argument(
        "--radius",
        type=parse_radius,
        default=DEFAULT_RADIUS,
        help="Red title background corner radius in pixels (default: 8)",
    )
    parser.add_argument("--second-title", help="Optional subtitle drawn below the main title")
    parser.add_argument("--emoji", help="Optional emoji drawn above the main title")
    parser.add_argument(
        "--second-font-scale",
        type=parse_font_scale,
        default=DEFAULT_SECOND_FONT_SCALE,
        help="Second title font size as a fraction of image height (default: 0.06)",
    )
    parser.add_argument(
        "--emoji-scale",
        type=parse_font_scale,
        default=DEFAULT_EMOJI_SCALE,
        help="Emoji size as a fraction of image height (default: 0.1)",
    )
    args = parser.parse_args()

    try:
        output_path = generate_thumbnail(
            args.video,
            args.title,
            output_path=args.output,
            position=args.position,
            size=args.size,
            margin=args.margin,
            padding=args.padding,
            font_scale=args.font_scale,
            radius=args.radius,
            second_title=args.second_title,
            emoji=args.emoji,
            second_font_scale=args.second_font_scale,
            emoji_scale=args.emoji_scale,
        )
    except Exception as exc:
        print(f"Thumbnail generation failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Thumbnail saved: {output_path}")


if __name__ == "__main__":
    main()
