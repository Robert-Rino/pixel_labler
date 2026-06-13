from abc import ABC, abstractmethod
from dataclasses import dataclass

import twitch_download
import yt_download


@dataclass
class DownloadResult:
    platform: str
    output_dir: str | None
    trigger_folder: str | None = None


class Downloader(ABC):
    platform = "generic"

    def __init__(self, root_dir="."):
        self.root_dir = root_dir

    @staticmethod
    @abstractmethod
    def supports(url):
        """Return True when this downloader can handle the URL."""

    @abstractmethod
    def download(self, url, **options):
        """Download a URL and return a DownloadResult."""


class YTDownloader(Downloader):
    platform = "youtube"

    @staticmethod
    def supports(url):
        return yt_download.validate_youtube_url(url)

    def download(self, url, **options):
        force_transcript = options.pop("force_transcript", False)
        extract_audio = options.pop("extract_audio", True)

        if options:
            unknown = ", ".join(sorted(options))
            raise TypeError(f"Unsupported YouTube download options: {unknown}")

        output_dir = yt_download.download_video(
            url,
            root_dir=self.root_dir,
            force_transcript=force_transcript,
            extract_audio=extract_audio,
        )
        return DownloadResult(platform=self.platform, output_dir=output_dir)


class TwitchDownloader(Downloader):
    platform = "twitch"

    @staticmethod
    def supports(url):
        return "twitch.tv" in url

    def download(self, url, **options):
        audio = options.pop("audio", True)
        start_min = options.pop("start_min", None)
        duration_min = options.pop("duration_min", None)

        if options:
            unknown = ", ".join(sorted(options))
            raise TypeError(f"Unsupported Twitch download options: {unknown}")

        result = twitch_download.download_video(
            url,
            root_dir=self.root_dir,
            audio=audio,
            start_min=start_min,
            duration_min=duration_min,
        )
        if result is None:
            return DownloadResult(platform=self.platform, output_dir=None)

        output_dir, trigger_folder = result
        return DownloadResult(
            platform=self.platform,
            output_dir=output_dir,
            trigger_folder=trigger_folder,
        )


def get_downloader(url, root_dir="."):
    for downloader_class in (YTDownloader, TwitchDownloader):
        if downloader_class.supports(url):
            return downloader_class(root_dir=root_dir)
    raise ValueError(f"No downloader available for URL: {url}")
