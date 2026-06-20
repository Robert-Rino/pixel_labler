import os
import tempfile
import unittest
from unittest.mock import MagicMock

import numpy as np
from PIL import Image

from thumbnail import (
    DEFAULT_PADDING,
    TITLE_BOLD_OPACITY,
    _draw_bold_multiline_text,
    _title_bold_width,
    create_thumbnail,
    parse_font_scale,
    parse_margin,
    parse_padding,
    parse_radius,
    parse_size,
    title_box,
)


class TestThumbnailGenerator(unittest.TestCase):
    def test_default_title_padding_is_compact(self):
        self.assertEqual(DEFAULT_PADDING, 16)

    def test_parse_size_accepts_width_by_height(self):
        self.assertEqual(parse_size("1280x720"), (1280, 720))

    def test_parse_size_rejects_invalid_value(self):
        with self.assertRaises(Exception):
            parse_size("1280")

    def test_parse_margin_and_padding_reject_negative_values(self):
        with self.assertRaises(Exception):
            parse_margin("-1")
        with self.assertRaises(Exception):
            parse_padding("-1")

    def test_parse_font_scale_rejects_non_positive_values(self):
        with self.assertRaises(Exception):
            parse_font_scale("0")

    def test_parse_radius_rejects_negative_values(self):
        with self.assertRaises(Exception):
            parse_radius("-1")

    def test_title_box_positions(self):
        self.assertEqual(title_box((1280, 720), (300, 80), "top", margin=20, padding=10), (480, 20, 800, 120))
        self.assertEqual(title_box((1280, 720), (300, 80), "middle", margin=20, padding=10), (480, 310, 800, 410))
        self.assertEqual(title_box((1280, 720), (300, 80), "down", margin=20, padding=10), (480, 600, 800, 700))

    def test_title_bold_width_stays_subtle(self):
        self.assertEqual(_title_bold_width(24), 1)
        self.assertEqual(_title_bold_width(72), 2)

    def test_title_bold_offsets_use_reduced_opacity(self):
        draw = MagicMock()

        _draw_bold_multiline_text(
            draw,
            (10, 20),
            "標題",
            MagicMock(size=48),
            (255, 255, 255),
            bold_width=1,
            bold_opacity=TITLE_BOLD_OPACITY,
        )

        offset_calls = draw.multiline_text.call_args_list[:-1]
        center_call = draw.multiline_text.call_args_list[-1]
        self.assertTrue(offset_calls)
        self.assertTrue(
            all(
                call.kwargs["fill"] == (255, 255, 255, TITLE_BOLD_OPACITY)
                for call in offset_calls
            )
        )
        self.assertEqual(center_call.kwargs["fill"], (255, 255, 255))

    def test_create_thumbnail_writes_image(self):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:, :] = (50, 80, 120)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "thumb.jpg")
            create_thumbnail(frame, "Big Stream Moment", output_path, size=(640, 360))

            self.assertTrue(os.path.exists(output_path))
            with Image.open(output_path) as image:
                self.assertEqual(image.size, (480, 360))

    def test_create_thumbnail_accepts_chinese_title(self):
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        frame[:, :] = (40, 60, 90)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "thumb.jpg")
            create_thumbnail(frame, "測試文字", output_path, size=(640, 360), font_scale=0.06)

            self.assertTrue(os.path.exists(output_path))

    def test_create_thumbnail_accepts_optional_layers(self):
        frame = np.zeros((640, 360, 3), dtype=np.uint8)
        frame[:, :] = (30, 50, 80)

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "thumb.jpg")
            create_thumbnail(
                frame,
                "婚後一年就想",
                output_path,
                size=(360, 640),
                second_title="離婚?",
                emoji="😲",
            )

            self.assertTrue(os.path.exists(output_path))


if __name__ == "__main__":
    unittest.main()
