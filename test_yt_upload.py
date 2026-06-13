import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, mock_open, patch

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

    def test_parse_publish_time_supports_z_suffix(self):
        publish_time = yt_upload.parse_publish_time("2026-06-20T15:00:00Z")

        self.assertEqual(
            publish_time,
            datetime(2026, 6, 20, 15, 0, tzinfo=timezone.utc),
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
        )

        self.assertEqual(body["snippet"]["title"], "My Title")
        self.assertEqual(body["snippet"]["description"], "Desc")
        self.assertEqual(body["snippet"]["categoryId"], "24")
        self.assertEqual(body["snippet"]["tags"], ["one", "two"])
        self.assertEqual(body["status"]["privacyStatus"], "private")
        self.assertEqual(body["status"]["publishAt"], "2026-06-20T15:00:00Z")

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

        service = MagicMock()
        service.videos.return_value = videos
        service.thumbnails.return_value = thumbnails
        mock_build.return_value = service

        result = yt_upload.upload_video(
            "video.mp4",
            title="My Title",
            thumbnail_file="thumb.jpg",
            publish_time=datetime(2026, 6, 20, 15, 0, tzinfo=timezone.utc),
            description="Desc",
            hashtags=["news"],
            client_secrets_file="client_secret.json",
            token_file="token.json",
        )

        self.assertEqual(result, "video123")
        self.assertEqual(videos.insert.call_args.kwargs["body"]["snippet"]["description"], "Desc\n#news")
        mock_media_file_upload.assert_any_call(
            "video.mp4",
            chunksize=1024 * 1024 * 8,
            resumable=True,
        )
        mock_media_file_upload.assert_any_call("thumb.jpg")
        videos.insert.assert_called_once()
        thumbnails.set.assert_called_once()
        thumbnails.set.return_value.execute.assert_called_once()

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
