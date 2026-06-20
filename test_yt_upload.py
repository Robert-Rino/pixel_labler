import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, mock_open, patch
import os
import tempfile

import yt_upload


class TestYouTubeUpload(unittest.TestCase):
    def test_normalize_hashtags_adds_hash_and_dedupes(self):
        self.assertEqual(
            yt_upload.normalize_hashtags(["news", "#clips", "news", "  "] ),
            ["#news", "#clips"],
        )

    def test_compose_description_appends_hashtags(self):
        self.assertEqual(
            yt_upload.compose_description("Hello", ["news", "#clips"]),
            "Hello\n#news\n#clips",
        )

    def test_compose_description_skips_duplicate_hashtags(self):
        self.assertEqual(
            yt_upload.compose_description("#asmongold #asmongold翻譯", ["asmongold", "asmongold翻譯"]),
            "#asmongold #asmongold翻譯",
        )

    def test_build_title_from_metadata_uses_emoji_title_and_second_title(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            metadata_path = os.path.join(tmpdir, "metadata.md")
            with open(metadata_path, "w", encoding="utf-8") as metadata:
                metadata.write(
                    "## 2\n"
                    "- Emoji: 🕊\n"
                    "- Title: 神的聲音\n"
                    "- Second-title: 阿斯～\n"
                )

            self.assertEqual(
                yt_upload.build_title_from_metadata(metadata_path),
                "🕊 神的聲音 阿斯～",
            )

    def test_build_title_from_metadata_skips_empty_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            metadata_path = os.path.join(tmpdir, "metadata.md")
            with open(metadata_path, "w", encoding="utf-8") as metadata:
                metadata.write(
                    "## 1\n"
                    "- Emoji: 🚓\n"
                    "- Title: 抓到你了小子\n"
                    "- Second-title:\n"
                )

            self.assertEqual(
                yt_upload.build_title_from_metadata(metadata_path),
                "🚓 抓到你了小子",
            )

    def test_parse_twitch_crop_records_reads_record_fields(self):
        markdown = """# Twitch Crop Records
- URL: https://www.twitch.tv/videos/123

## 1
- Emoji: 💥
- Title: 這該死的緊張感
- Second-title: 峰迴路轉
- Start: 03:35:45
- End: 03:38:17
"""

        records = yt_upload.parse_twitch_crop_records(markdown)

        self.assertEqual(
            records,
            [
                {
                    "number": "1",
                    "emoji": "💥",
                    "title": "這該死的緊張感",
                    "second-title": "峰迴路轉",
                    "start": "03:35:45",
                    "end": "03:38:17",
                }
            ],
        )

    def test_build_batch_uploads_falls_back_to_custom_folder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(
                os.path.join(tmpdir, "twitch-crop-records.md"),
                "w",
                encoding="utf-8",
            ) as records:
                records.write(
                    "# Twitch Crop Records\n"
                    "\n"
                    "## 1\n"
                    "- Emoji: 🐶\n"
                    "- Title: 臘腸滑板看過嗎\n"
                    "- Second-title:\n"
                    "- Start: 00:56:47\n"
                    "- End: 00:57:15\n"
                )
            clip_dir = os.path.join(tmpdir, "Custom_005647_005715")
            os.makedirs(clip_dir)
            video_path = os.path.join(clip_dir, "result.mp4")
            thumbnail_path = os.path.join(clip_dir, "thumbnail.jpg")
            open(video_path, "wb").close()
            open(thumbnail_path, "wb").close()

            uploads, skipped = yt_upload.build_batch_uploads(tmpdir)

        self.assertEqual([], skipped)
        self.assertEqual("🐶 臘腸滑板看過嗎", uploads[0]["title"])
        self.assertEqual(video_path, uploads[0]["video_file"])
        self.assertEqual(thumbnail_path, uploads[0]["thumbnail_file"])

    def test_build_batch_uploads_uses_custom_folder_when_title_folder_has_no_video(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(
                os.path.join(tmpdir, "twitch-crop-records.md"),
                "w",
                encoding="utf-8",
            ) as records:
                records.write(
                    "# Twitch Crop Records\n"
                    "\n"
                    "## 1\n"
                    "- Emoji: 💥\n"
                    "- Title: 這該死的緊張感\n"
                    "- Second-title: 峰迴路轉\n"
                    "- Start: 03:35:45\n"
                    "- End: 03:38:17\n"
                )
            os.makedirs(os.path.join(tmpdir, "這該死的緊張感"))
            custom_dir = os.path.join(tmpdir, "Custom_033545_033817")
            os.makedirs(custom_dir)
            video_path = os.path.join(custom_dir, "result.mp4")
            open(video_path, "wb").close()

            uploads, skipped = yt_upload.build_batch_uploads(tmpdir)

        self.assertEqual([], skipped)
        self.assertEqual(video_path, uploads[0]["video_file"])

    def test_build_batch_uploads_prefers_title_folder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(
                os.path.join(tmpdir, "twitch-crop-records.md"),
                "w",
                encoding="utf-8",
            ) as records:
                records.write(
                    "# Twitch Crop Records\n"
                    "\n"
                    "## 1\n"
                    "- Emoji: 🔧\n"
                    "- Title: 手搓主機板嗎\n"
                    "- Second-title: 真有溫度\n"
                    "- Start: 03:38:28\n"
                    "- End: 03:39:25\n"
                )
            clip_dir = os.path.join(tmpdir, "手搓主機板嗎")
            os.makedirs(clip_dir)
            video_path = os.path.join(clip_dir, "result.mp4")
            open(video_path, "wb").close()

            uploads, skipped = yt_upload.build_batch_uploads(tmpdir)

        self.assertEqual([], skipped)
        self.assertEqual("🔧 手搓主機板嗎 真有溫度", uploads[0]["title"])
        self.assertEqual(video_path, uploads[0]["video_file"])
        self.assertIsNone(uploads[0]["thumbnail_file"])

    def test_parse_publish_time_supports_z_suffix(self):
        publish_time = yt_upload.parse_publish_time("2026-06-20T15:00:00Z")

        self.assertEqual(
            publish_time,
            datetime(2026, 6, 20, 15, 0, tzinfo=timezone.utc),
        )

    def test_resolve_publish_time_defaults_to_24_hours_later(self):
        now = datetime(2026, 6, 20, 10, 30, tzinfo=timezone.utc)

        publish_time = yt_upload.resolve_publish_time(now=now)

        self.assertEqual(
            publish_time,
            datetime(2026, 6, 21, 10, 30, tzinfo=timezone.utc),
        )

    def test_resolve_publish_time_can_disable_scheduling(self):
        now = datetime(2026, 6, 20, 10, 30, tzinfo=timezone.utc)

        publish_time = yt_upload.resolve_publish_time(
            no_schedule=True,
            now=now,
        )

        self.assertIsNone(publish_time)

    def test_resolve_publish_time_prefers_explicit_value(self):
        publish_time = yt_upload.resolve_publish_time(
            "2026-06-25T15:00:00Z",
            now=datetime(2026, 6, 20, 10, 30, tzinfo=timezone.utc),
        )

        self.assertEqual(
            publish_time,
            datetime(2026, 6, 25, 15, 0, tzinfo=timezone.utc),
        )

    def test_build_video_body_schedules_private_publish(self):
        publish_time = datetime(2026, 6, 20, 15, 0, tzinfo=timezone.utc)

        body = yt_upload.build_video_body(
            title="My Title",
            description="Desc",
            privacy="public",
            publish_time=publish_time,
            tags=["one", "two"],
            category_id="24",
            made_for_kids=False,
        )

        self.assertEqual(body["snippet"]["title"], "My Title")
        self.assertEqual(body["snippet"]["description"], "Desc")
        self.assertEqual(body["snippet"]["categoryId"], "24")
        self.assertEqual(body["snippet"]["tags"], ["one", "two"])
        self.assertEqual(body["status"]["privacyStatus"], "private")
        self.assertEqual(body["status"]["publishAt"], "2026-06-20T15:00:00Z")
        self.assertFalse(body["status"]["selfDeclaredMadeForKids"])

    def test_add_video_to_playlist_inserts_playlist_item(self):
        service = MagicMock()

        yt_upload.add_video_to_playlist(
            service,
            "video123",
            "playlist456",
            position=2,
        )

        body = service.playlistItems.return_value.insert.call_args.kwargs["body"]
        self.assertEqual(body["snippet"]["playlistId"], "playlist456")
        self.assertEqual(body["snippet"]["position"], 2)
        self.assertEqual(
            body["snippet"]["resourceId"],
            {"kind": "youtube#video", "videoId": "video123"},
        )
        service.playlistItems.return_value.insert.assert_called_once_with(
            part="snippet",
            body=body,
        )
        service.playlistItems.return_value.insert.return_value.execute.assert_called_once()

    def test_write_video_id_writes_trailing_newline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "youtube_video_id.txt")

            yt_upload.write_video_id("video123", output_path)

            with open(output_path, "r", encoding="utf-8") as video_id_file:
                self.assertEqual(video_id_file.read(), "video123\n")

    @patch("yt_upload.write_video_id")
    @patch("yt_upload.MediaFileUpload")
    @patch("yt_upload.build")
    @patch("yt_upload.load_credentials")
    @patch("os.path.isfile", return_value=True)
    def test_upload_video_uploads_thumbnail_and_returns_id(
        self,
        mock_isfile,
        mock_load_credentials,
        mock_build,
        mock_media_file_upload,
        mock_write_video_id,
    ):
        mock_load_credentials.return_value = MagicMock()

        request = MagicMock()
        request.next_chunk.side_effect = [
            (MagicMock(progress=lambda: 0.5), None),
            (None, {"id": "video123"}),
        ]

        videos = MagicMock()
        videos.insert.return_value = request

        thumbnails = MagicMock()
        playlist_items = MagicMock()

        service = MagicMock()
        service.videos.return_value = videos
        service.thumbnails.return_value = thumbnails
        service.playlistItems.return_value = playlist_items
        mock_build.return_value = service

        result = yt_upload.upload_video(
            "video.mp4",
            title="My Title",
            thumbnail_file="thumb.jpg",
            publish_time=datetime(2026, 6, 20, 15, 0, tzinfo=timezone.utc),
            description="Desc",
            hashtags=["news"],
            made_for_kids=False,
            playlist_id="playlist456",
            client_secrets_file="client_secret.json",
            token_file="token.json",
            video_id_file="youtube_video_id.txt",
        )

        self.assertEqual(result, "video123")
        self.assertEqual(
            videos.insert.call_args.kwargs["body"]["snippet"]["description"],
            "Desc\n#news",
        )
        mock_write_video_id.assert_called_once_with(
            "video123",
            "youtube_video_id.txt",
        )
        mock_media_file_upload.assert_any_call(
            "video.mp4",
            chunksize=1024 * 1024 * 8,
            resumable=True,
        )
        mock_media_file_upload.assert_any_call("thumb.jpg")
        videos.insert.assert_called_once()
        thumbnails.set.assert_called_once()
        thumbnails.set.return_value.execute.assert_called_once()
        playlist_items.insert.assert_called_once()
        playlist_items.insert.return_value.execute.assert_called_once()

    @patch("yt_upload.write_video_id")
    @patch("yt_upload.MediaFileUpload")
    @patch("yt_upload.build")
    @patch("yt_upload.load_credentials")
    @patch("os.path.isfile", return_value=True)
    def test_upload_video_saves_id_before_thumbnail_failure(
        self,
        mock_isfile,
        mock_load_credentials,
        mock_build,
        mock_media_file_upload,
        mock_write_video_id,
    ):
        request = MagicMock()
        request.next_chunk.return_value = (None, {"id": "video123"})

        service = MagicMock()
        service.videos.return_value.insert.return_value = request
        service.thumbnails.return_value.set.return_value.execute.side_effect = (
            RuntimeError("thumbnail failed")
        )
        mock_build.return_value = service
        mock_load_credentials.return_value = MagicMock()

        with self.assertRaisesRegex(RuntimeError, "thumbnail failed"):
            yt_upload.upload_video(
                "video.mp4",
                title="My Title",
                thumbnail_file="thumb.jpg",
                video_id_file="youtube_video_id.txt",
            )

        mock_write_video_id.assert_called_once_with(
            "video123",
            "youtube_video_id.txt",
        )

    @patch("yt_upload.InstalledAppFlow")
    @patch("yt_upload.Credentials")
    def test_load_credentials_writes_token_file(self, mock_credentials, mock_flow):
        mock_credentials.from_authorized_user_file.return_value = None
        mock_flow.from_client_secrets_file.return_value = MagicMock(
            run_local_server=MagicMock(
                return_value=MagicMock(to_json=MagicMock(return_value='{"token": "x"}'))
            )
        )

        with patch("os.path.exists", side_effect=lambda path: path == "client_secret.json"), patch(
            "builtins.open", mock_open()
        ):
            creds = yt_upload.load_credentials(
                "client_secret.json",
                "token.json",
                use_console=False,
            )

        self.assertIsNotNone(creds)
        mock_flow.from_client_secrets_file.assert_called_once_with(
            "client_secret.json",
            yt_upload.SCOPES,
        )


if __name__ == "__main__":
    unittest.main()
