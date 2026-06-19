import os
import tempfile
import unittest

import encode_subtitle


class TestEncodeSubtitle(unittest.TestCase):
    def test_default_ass_style_is_bold_white_with_black_outline_and_box(self):
        srt_text = """1
00:00:00,000 --> 00:00:01,000
這是女性專用停車位
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            srt_path = os.path.join(tmpdir, "subtitle.srt")
            ass_path = os.path.join(tmpdir, "subtitle.ass")
            with open(srt_path, "w", encoding="utf-8") as srt_file:
                srt_file.write(srt_text)

            encode_subtitle.write_positioned_ass(srt_path, ass_path)

            with open(ass_path, "r", encoding="utf-8") as ass_file:
                ass_text = ass_file.read()

        self.assertIn(
            "Style: Default,Heiti TC,64,&H00FFFFFF,&H000000FF,"
            "&H00000000,&HE0000000,-1,0,0,0,100,100,0,0,3,5,0,8,0,0,0,1",
            ass_text,
        )

    def test_image_overlay_has_semi_transparent_background(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            overlay_path = os.path.join(tmpdir, "subtitle.png")

            encode_subtitle.render_subtitle_overlay("這是女性專用停車位", overlay_path)

            image = encode_subtitle.Image.open(overlay_path)
            image.load()

        self.assertEqual("RGBA", image.mode)
        background_alpha = image.getpixel((image.width // 2, 2))[3]
        self.assertEqual(encode_subtitle.IMAGE_BOX_FILL[3], background_alpha)
        self.assertLess(background_alpha, 255)

    def test_parse_srt_image_blocks_uses_seconds_and_plain_text(self):
        srt_text = """1
00:00:01,250 --> 00:00:03,500
第一行
第二行
"""

        blocks = encode_subtitle.parse_srt_image_blocks(srt_text)

        self.assertEqual([(1.25, 3.5, "第一行\n第二行")], blocks)


if __name__ == "__main__":
    unittest.main()
