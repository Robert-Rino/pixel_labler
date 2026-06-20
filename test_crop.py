import os
import tempfile
import unittest
from unittest.mock import Mock, patch

import crop


class TestCropRecords(unittest.TestCase):
    def test_parse_twitch_crop_records(self):
        markdown = """# Twitch Crop Records
- URL: https://www.twitch.tv/videos/2795031392

## 1
- Emoji: 🚓
- Title: 抓到你了小子
- Second-title:
- Start: 04:50:57
- End: 04:51:28

## 2
- Emoji: 🕊
- Title: 神的聲音
- Second-title:
- Start: 04:52:23
- End: 04:54:13
"""

        records = crop.parse_twitch_crop_records(markdown)

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["title"], "抓到你了小子")
        self.assertEqual(records[0]["start"], "04:50:57")
        self.assertEqual(records[0]["end"], "04:51:28")
        self.assertIn("- Emoji: 🚓", records[0]["metadata"])
        self.assertEqual(records[1]["title"], "神的聲音")

    @patch("crop.burn_thumbnail_as_first_frame", return_value=True)
    @patch("crop.generate_thumbnail")
    @patch("crop.encode_subtitle")
    @patch("crop.transcribe_video")
    @patch("crop.ffmpeg.crop", return_value=True)
    def test_process_twitch_crop_records_creates_each_clip_metadata(
        self,
        mock_crop,
        mock_transcribe,
        mock_encode_subtitle,
        mock_generate_thumbnail,
        mock_burn_thumbnail,
    ):
        records_md = """# Twitch Crop Records
- URL: https://www.twitch.tv/videos/2795031392

## 1
- Emoji: 🚓
- Title: 抓到你了小子
- Second-title: 你跑不掉
- Start: 04:50:57
- End: 04:51:28

## 2
- Emoji: 🕊
- Title: 神的聲音
- Second-title:
- Start: 04:52:23
- End: 04:54:13
"""

        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "original.mp4"), "wb") as f:
                f.write(b"video")
            with open(os.path.join(tmpdir, "twitch-crop-records.md"), "w", encoding="utf-8") as f:
                f.write(records_md)

            crop.process(tmpdir, crop_cam="cam", crop_screen="screen")

            self.assertEqual(mock_crop.call_count, 2)
            self.assertEqual(mock_transcribe.call_count, 2)
            self.assertEqual(mock_encode_subtitle.call_count, 2)
            self.assertEqual(mock_generate_thumbnail.call_count, 2)
            self.assertEqual(mock_burn_thumbnail.call_count, 2)

            first_call = mock_crop.call_args_list[0].args
            second_call = mock_crop.call_args_list[1].args
            self.assertEqual(first_call[1], "04:50:57")
            self.assertEqual(first_call[2], "04:51:28")
            self.assertEqual(second_call[1], "04:52:23")
            self.assertEqual(second_call[2], "04:54:13")

            first_encode_args = mock_encode_subtitle.call_args_list[0].args
            self.assertEqual(first_encode_args[0], os.path.join(tmpdir, "抓到你了小子", "stacked.mp4"))
            self.assertEqual(first_encode_args[1], os.path.join(tmpdir, "抓到你了小子", "result-zh.srt"))
            self.assertEqual(first_encode_args[2], os.path.join(tmpdir, "抓到你了小子", "result.mp4"))
            first_thumbnail_args = mock_generate_thumbnail.call_args_list[0].args
            first_thumbnail_kwargs = mock_generate_thumbnail.call_args_list[0].kwargs
            self.assertEqual(first_thumbnail_args[0], os.path.join(tmpdir, "抓到你了小子", "stacked.mp4"))
            self.assertEqual(first_thumbnail_args[1], "抓到你了小子")
            self.assertEqual(
                first_thumbnail_kwargs["output_path"],
                os.path.join(tmpdir, "抓到你了小子", "thumbnail.jpg"),
            )
            self.assertEqual(first_thumbnail_kwargs["second_title"], "你跑不掉")
            self.assertEqual(first_thumbnail_kwargs["emoji"], "🚓")
            mock_burn_thumbnail.assert_any_call(
                os.path.join(tmpdir, "抓到你了小子", "result.mp4"),
                os.path.join(tmpdir, "抓到你了小子", "thumbnail.jpg"),
            )

            first_metadata_path = os.path.join(tmpdir, "抓到你了小子", "metadata.md")
            second_metadata_path = os.path.join(tmpdir, "神的聲音", "metadata.md")

            with open(first_metadata_path, "r", encoding="utf-8") as f:
                first_metadata = f.read()
            with open(second_metadata_path, "r", encoding="utf-8") as f:
                second_metadata = f.read()

            self.assertIn("## 1", first_metadata)
            self.assertIn("- Title: 抓到你了小子", first_metadata)
            self.assertNotIn("# Twitch Crop Records", first_metadata)
            self.assertIn("## 2", second_metadata)
            self.assertIn("- Title: 神的聲音", second_metadata)

    @patch("crop.burn_thumbnail_as_first_frame", return_value=True)
    @patch("crop.generate_thumbnail")
    @patch("crop.encode_subtitle")
    @patch("crop.transcribe_video")
    @patch("crop.ffmpeg.crop", return_value=True)
    def test_process_start_end_cli_mode(
        self,
        mock_crop,
        mock_transcribe,
        mock_encode_subtitle,
        mock_generate_thumbnail,
        mock_burn_thumbnail,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "original.mp4"), "wb") as f:
                f.write(b"video")

            crop.process(
                tmpdir,
                crop_cam="cam",
                crop_screen="screen",
                start_arg="00:01:00",
                end_arg="00:01:10",
            )

            mock_crop.assert_called_once()
            mock_encode_subtitle.assert_called_once()
            mock_generate_thumbnail.assert_called_once()
            args = mock_crop.call_args.args
            self.assertEqual(args[1], "00:01:00")
            self.assertEqual(args[2], "00:01:10")

            metadata_path = os.path.join(tmpdir, "Custom_000100_000110", "metadata.md")
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = f.read()

            self.assertIn("## CLI", metadata)
            self.assertIn("- Start: 00:01:00", metadata)
            self.assertIn("- End: 00:01:10", metadata)
            mock_transcribe.assert_called_once()
            mock_burn_thumbnail.assert_called_once_with(
                os.path.join(tmpdir, "Custom_000100_000110", "result.mp4"),
                os.path.join(tmpdir, "Custom_000100_000110", "thumbnail.jpg"),
            )

    @patch("crop.subprocess.run")
    def test_burn_thumbnail_as_first_frame_replaces_video(self, mock_run):
        mock_run.return_value = Mock(returncode=0, stderr="")

        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "result.mp4")
            thumbnail_path = os.path.join(tmpdir, "thumbnail.jpg")
            temp_path = os.path.join(tmpdir, ".thumbnail-first-frame.mp4")
            with open(video_path, "wb") as video:
                video.write(b"original")
            with open(thumbnail_path, "wb") as thumbnail:
                thumbnail.write(b"thumbnail")
            with open(temp_path, "wb") as output:
                output.write(b"updated")

            success = crop.burn_thumbnail_as_first_frame(video_path, thumbnail_path)

            self.assertTrue(success)
            with open(video_path, "rb") as video:
                self.assertEqual(video.read(), b"updated")
            command = mock_run.call_args.args[0]
            filter_complex = command[command.index("-filter_complex") + 1]
            self.assertIn("overlay=0:0:enable='eq(n,0)'", filter_complex)
            self.assertIn("0:a?", command)
            self.assertFalse(os.path.exists(temp_path))

    @patch("crop.subprocess.run")
    def test_burn_thumbnail_as_first_frame_keeps_video_on_failure(self, mock_run):
        mock_run.return_value = Mock(returncode=1, stderr="failed")

        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "result.mp4")
            thumbnail_path = os.path.join(tmpdir, "thumbnail.jpg")
            with open(video_path, "wb") as video:
                video.write(b"original")
            with open(thumbnail_path, "wb") as thumbnail:
                thumbnail.write(b"thumbnail")

            success = crop.burn_thumbnail_as_first_frame(video_path, thumbnail_path)

            self.assertFalse(success)
            with open(video_path, "rb") as video:
                self.assertEqual(video.read(), b"original")


if __name__ == "__main__":
    unittest.main()
