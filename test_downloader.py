import unittest
from unittest.mock import patch

from downloader import DownloadResult, TwitchDownloader, YTDownloader, get_downloader


class TestDownloaderFacade(unittest.TestCase):
    def test_get_downloader_returns_youtube_downloader(self):
        downloader = get_downloader(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            root_dir="downloads",
        )

        self.assertIsInstance(downloader, YTDownloader)
        self.assertEqual(downloader.root_dir, "downloads")

    def test_get_downloader_returns_twitch_downloader(self):
        downloader = get_downloader(
            "https://www.twitch.tv/videos/12345678",
            root_dir="downloads",
        )

        self.assertIsInstance(downloader, TwitchDownloader)
        self.assertEqual(downloader.root_dir, "downloads")

    def test_get_downloader_rejects_unknown_url(self):
        with self.assertRaises(ValueError):
            get_downloader("https://example.com/video")

    @patch("yt_download.download_video")
    def test_youtube_download_delegates_to_existing_logic(self, mock_download_video):
        mock_download_video.return_value = "/tmp/youtube-video"

        result = YTDownloader(root_dir="downloads").download(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            force_transcript=True,
            extract_audio=False,
        )

        mock_download_video.assert_called_once_with(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            root_dir="downloads",
            force_transcript=True,
            extract_audio=False,
        )
        self.assertEqual(
            result,
            DownloadResult(platform="youtube", output_dir="/tmp/youtube-video"),
        )

    @patch("twitch_download.download_video")
    def test_twitch_download_delegates_to_existing_logic(self, mock_download_video):
        mock_download_video.return_value = ("/tmp/twitch-video", "trigger-folder")

        result = TwitchDownloader(root_dir="downloads").download(
            "https://www.twitch.tv/videos/12345678",
            audio=False,
            start_min=10,
            duration_min=20,
        )

        mock_download_video.assert_called_once_with(
            "https://www.twitch.tv/videos/12345678",
            root_dir="downloads",
            audio=False,
            start_min=10,
            duration_min=20,
        )
        self.assertEqual(
            result,
            DownloadResult(
                platform="twitch",
                output_dir="/tmp/twitch-video",
                trigger_folder="trigger-folder",
            ),
        )


if __name__ == "__main__":
    unittest.main()
