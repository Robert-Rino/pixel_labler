import unittest
from unittest.mock import patch, MagicMock
import os
import twitch_download

class TestTwitchDownload(unittest.TestCase):
    @patch('yt_dlp.YoutubeDL')
    @patch('subprocess.run')
    @patch('transcript.transcribe_video')
    @patch('n8n.trigger')
    def test_download_video_configures_rechat(self, mock_n8n, mock_transcribe, mock_subprocess, mock_yt_dlp):
        # Setup
        url = "https://www.twitch.tv/videos/12345678"
        mock_instance = mock_yt_dlp.return_value.__enter__.return_value
        
        # Mock extract_info to return some metadata
        mock_instance.extract_info.return_value = {
            'uploader': 'test_user',
            'upload_date': '20230101',
            'timestamp': 1672531200,
            'title': 'Test VOD',
            'description': 'Test Description',
            'duration': 3600
        }
        
        # We need to simulate the file creation because the code checks if it exists
        # Actually, let's just check the arguments passed to YoutubeDL
        
        # Run
        with patch('os.path.exists', return_value=False):
            with patch('os.makedirs'):
                with patch('builtins.open', unittest.mock.mock_open()):
                    try:
                        twitch_download.download_video(url, root_dir="test_root", audio=False)
                    except SystemExit:
                        pass # It might exit because we are mocking too much and files don't exist
        
        # Verify
        # Check if YoutubeDL was called with rechat options
        # YoutubeDL is called twice: once for metadata, once for video.
        # We care about the second call (the one that does the download)
        
        calls = mock_yt_dlp.call_args_list
        found_rechat = False
        for call in calls:
            opts = call[0][0]
            if opts.get('writesubtitles') and 'rechat' in opts.get('subtitlesformat', ''):
                found_rechat = True
                break
        
        self.assertTrue(found_rechat, "yt-dlp was not configured to download rechat subtitles")

if __name__ == '__main__':
    unittest.main()
