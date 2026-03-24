import unittest
from unittest.mock import patch, MagicMock
import os
import twitch_download

class TestTwitchDownload(unittest.TestCase):
    @patch('chat_utils.download_chat')
    @patch('analyzer.analyze_video')
    @patch('yt_dlp.YoutubeDL')
    @patch('subprocess.run')
    @patch('transcript.transcribe_video')
    @patch('n8n.trigger')
    def test_download_video_calls_chat_utils(self, mock_n8n, mock_transcribe, mock_subprocess, mock_yt_dlp, mock_analyze, mock_download_chat):
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
        
        # We need a side effect for exists to handle the multiple checks
        # 1. output_dir (video_dir)
        # 2. output_original (original.mp4)
        # 3. rechat_path
        # 4. output_audio
        # 5. srt_output
        def exists_side_effect(path):
            if "original.mp4.rechat.json" in path: return False # Force chat download
            if "original.mp4" in path: return True # Pretend video exists after "download"
            if "metadata.md" in path: return True
            return False
            
        # Run
        with patch('os.path.exists', side_effect=exists_side_effect):
            with patch('os.makedirs'):
                with patch('builtins.open', unittest.mock.mock_open()):
                    try:
                        twitch_download.download_video(url, root_dir="test_root", audio=False)
                    except SystemExit:
                        pass 
        
        # Verify
        mock_download_chat.assert_called_once()
        args, kwargs = mock_download_chat.call_args
        self.assertEqual(args[0], url)
        self.assertTrue(args[1].endswith("original.mp4.rechat.json"))

if __name__ == '__main__':
    unittest.main()
